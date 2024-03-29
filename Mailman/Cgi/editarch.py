# Copyright (C) 1998,1999,2000,2001,2002 by the Free Software Foundation, Inc.
# Copyright (C) 1998,1999,2000,2001,2002 by the Free Software Foundation, Inc.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software 
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.

"""Script which implements admin editing of the list's archives."""

import os
import cgi
import errno
import signal
import mailbox
import time
import uu

from email.Header import decode_header, make_header
from email.Utils import _bdecode, _qdecode, parsedate_tz

from Mailman import Utils
from Mailman import MailList
from Mailman.htmlformat import *
from Mailman import Errors
from Mailman.Cgi import Auth
from Mailman.Logging.Syslog import syslog
from Mailman import i18n
from Mailman import mm_cfg
from Mailman.Mailbox import ArchiverMailbox
from Mailman import LockFile

_ = i18n._



def main():
    _ = i18n._
    doc = Document()

    # Set up the system default language
    i18n.set_language(mm_cfg.DEFAULT_SERVER_LANGUAGE)
    doc.set_language(mm_cfg.DEFAULT_SERVER_LANGUAGE)

    parts = Utils.GetPathPieces()
    if not parts:
        doc.AddItem(Header(2, _("List name is required.")))
        print doc.Format()
        return

    listname = parts[0].lower()
    try:
        mlist = MailList.MailList(listname, lock=0)
    except Errors.MMListError, e:
        # Avoid cross-site scripting attacks
        safelistname = Utils.websafe(listname)
        doc.AddItem(Header(2, _('No such list <em>%(safelistname)s</em>')))
        print doc.Format()
        syslog('error', 'No such list "%s": %s', listname, e)
        return

    # Now that we have a valid list, set the language to its default
    i18n.set_language(mlist.preferred_language)
    doc.set_language(mlist.preferred_language)

    # Must be authenticated to get any farther
    cgidata = cgi.FieldStorage()

    # Editing the archives for a list is limited to the list admin and
    # site admin.
    if not mlist.WebAuthenticate((mm_cfg.AuthListAdmin,
                                  mm_cfg.AuthSiteAdmin),
                                 cgidata.getvalue('adminpw', '')):
        if cgidata.has_key('admlogin'):
            # This is a re-authorization attempt
            msg = Bold(FontSize('+1', _('Authorization failed.'))).Format()
        else:
            msg = ''
        Auth.loginpage(mlist, 'admin', msg=msg)
        return

    realname = mlist.real_name
    name = mlist.ArchiveFileName()
    wname = name + '.working'

    try:
        os.stat(name)
    except (IOError, os.error):
        # no archive file
        doc.AddItem(Header(1, _('%(realname)s')))
        doc.AddItem(_('There are no archives to edit.'))
        doc.AddItem(mlist.GetMailmanFooter())
        print doc.Format()
        return

    # Open archive file
    archfile = open(name)
    mbox = mailbox.UnixMailbox(archfile)

    doc.SetTitle(_('%(realname)s -- Edit the list archives'))

    # If there are multiple parts, display a particular message or month
    if len(parts) > 1:
        # Make sure that parts[2] and up have good int values
        i = 2
        while i < len(parts):
            try:
                parts[i] = int(parts[i])
            except ValueError:
                parts[i] = 0
            i += 1

        if parts[1] == 'box' and len(parts) == 4:
            datestr = MakeDateString(parts[2], parts[3])
            doc.AddItem(Header(1, _('%(realname)s Archives -- ' + datestr)))
            DisplayBox(mlist, mbox, doc, parts[2], parts[3])
        elif parts[1] == 'message' and len(parts) == 3 and parts[2] > 0:
            msg_num = parts[2]
            doc.AddItem(Header(1, _('%(realname)s Archives -- Message')))
            doc.AddItem('<hr>\n')
    	    l = Link(mlist.GetScriptURL('editarch') + '/confirm/' + str(msg_num), _('Delete this message'))
            doc.AddItem('<div align="center">')
            doc.AddItem(l)
            doc.AddItem('</div>')

            doc.AddItem('\n<hr>\n')
            DisplayMessage(mlist, mbox, msg_num, doc, 0)
        elif parts[1] == 'confirm' and len(parts) == 3 and parts[2] > 0:
            msg_num = parts[2]
            doc.AddItem(Header(1, _('%(realname)s Archives -- Delete Message?')))
            doc.AddItem('<hr>\n')
    	    l = Link(mlist.GetScriptURL('editarch') + '/delete/' + str(msg_num), _('Confirm delete'))
            doc.AddItem('<div align="center">')
            doc.AddItem(l)
            doc.AddItem('\n<br>\n')
            doc.AddItem(_('(This may take a few seconds.  Please be patient.)'))
            doc.AddItem('\n</div>')

            doc.AddItem('<hr>\n')
            DisplayMessage(mlist, mbox, msg_num, doc, 1)
        elif parts[1] == 'delete' and len(parts) == 3 and parts[2] > 0:
            msg_num = parts[2]
            DeleteMessage(mlist, mbox, msg_num, wname, doc)
            os.rename(wname, name)
            TagForArchProcessing(mlist)

            print 'Content-type: text/html\n\n'
            print '<meta http-equiv="Refresh" content="0; url=' + mlist.GetScriptURL('editarch') + '/deleted/' + str(msg_num) + '">'
            l = Link(mlist.GetScriptURL('editarch') + '/deleted/' + str(msg_num), _('Click here to continue'))
            print '<html><body>' + l.Format() + '</body></html>'
            return

        elif parts[1] == 'deleted' and len(parts) == 3 and parts[2] > 0:
            msg_num = parts[2]
            doc.AddItem(Header(1, _('%(realname)s Archives -- Message Deleted')))
            doc.AddItem(_('<strong><em>Important:</em></strong> It\'s best to use the links below to continue editing.  If you do go back, be sure to refresh/reload to be sure you are deleting the right message!\n<p>\n'))
            doc.AddItem('<p>\n<hr>\n<p>\n')
            doc.AddItem(_('Continue editing:\n<p>\n'))
            # if there is a previous message, display the link
            if msg_num > 1:
    	        l = Link(mlist.GetScriptURL('editarch') + '/message/' + str(msg_num - 1), _('<-- Previous Message'))
                doc.AddItem(l)
                doc.AddItem(' &nbsp;&nbsp;&nbsp;&nbsp; ')
            # the next message will have shifted to the current number
            l = Link(mlist.GetScriptURL('editarch') + '/message/' + str(msg_num), _('Next Message -->'))
            doc.AddItem(l)

            doc.AddItem('<p>\n')
            date = GetMessageDate(mbox, msg_num)
            if date is not None:
                l = Link(mlist.GetScriptURL('editarch') + '/box/' + str(date[0]) + '/' + str(date[1]), _('Back to ') + MakeDateString(date[0], date[1]))
                doc.AddItem(l)
                doc.AddItem('<p>\n')
            l = Link(mlist.GetScriptURL('editarch'), _('Go to main overview'))
            doc.AddItem(l)
        else:
            doc.AddItem(Header(1, _('%(realname)s Archives')))
            doc.AddItem('<p>\n<hr>\n<p>\n')
            l = Link(mlist.GetScriptURL('editarch'), _('Go to main overview'))
            doc.AddItem(l)
    # If just the listname, display the default overview
    else:
        doc.AddItem(Header(1, _('%(realname)s Archives -- Overview')))
	l = Link(mlist.GetBaseArchiveURL(), _('list archives'))
        doc.AddItem(_('Your changes will show up immediately here, but they will not show up immediately in the normal '))
        doc.AddItem(l)
        doc.AddItem(_('.  Archives will be reprocessed nightly, so check back tomorrow to see the changes.\n<p>\nMessages with non-standard date stamps will show up in the current month, so be sure to look there if you\'re having trouble finding a message.'))
        DisplayMonthOverview(mlist, mbox, doc)

    archfile.close()
    doc.AddItem(mlist.GetMailmanFooter())
    print doc.Format()

    return

# Display a single message by message number
def DisplayMessage(mlist, mbox, msg_num, doc, deleting):
    counter = 1
    while 1:
        m = mbox.next()
        if m is None:
            doc.AddItem(_('No messages matched.') + '\n<p>\n')
    	    l = Link(mlist.GetScriptURL('editarch'), _('Go to main overview'))
            doc.AddItem(l)
            break
        if counter == msg_num:
            body = decode_body(m, m.fp.read())
            header_date = m.get('date')
            header_from = decode(m.get('from'))
            header_subject = decode(m.get('subject'))
            doc.AddItem('<pre>\n')
            doc.AddItem(_('<b>Date:</b> ') + header_date + '\n')
            doc.AddItem(_('<b>From:</b> ') + html_quote(header_from) + '\n')
            doc.AddItem(_('<b>Subject:</b> ') + html_quote(header_subject) + '\n\n')
            doc.AddItem(html_quote(body) + '\n\n')
            doc.AddItem('</pre>\n')
            doc.AddItem('<p>\n')
            if not deleting:
                doc.AddItem('<p><hr><p>\n')
                if counter > 0:
    	            l = Link(mlist.GetScriptURL('editarch') + '/message/' + str(counter - 1), _('<-- Previous Message'))
                    doc.AddItem(l)
                    doc.AddItem(' &nbsp;&nbsp;&nbsp;&nbsp; ')
                l = Link(mlist.GetScriptURL('editarch') + '/message/' + str(counter + 1), _('Next Message -->'))
                doc.AddItem(l)
                doc.AddItem('<p>\n')
            date = GetDate(m)
            l = Link(mlist.GetScriptURL('editarch') + '/box/' + str(date[0]) + '/' + str(date[1]), _('Back to ') + MakeDateString(date[0], date[1]))
            doc.AddItem(l)
            doc.AddItem('<p>\n')
            l = Link(mlist.GetScriptURL('editarch'), _('Go to main overview'))
            doc.AddItem(l)
            break
        counter += 1

# Display a list of messages from the specified month/year
def DisplayBox(mlist, mbox, doc, year, month):
    counter = 1
    
    doc.AddItem('<ul>\n')
    while 1:
        try:
            m = mbox.next()
        except Errors.DiscardMessage:
            continue
        if m is None:
            break

        date = GetDate(m)
        thisyear = date[0]
        thismonth = date[1]

        if thismonth == month and thisyear == year:
            header_subject = decode(m.get('subject', 'n/a'))
            l = Link(mlist.GetScriptURL('editarch') + '/message/' + str(counter), html_quote(header_subject))
            doc.AddItem('<li>')
            doc.AddItem(l)
            header_from = decode(m.getaddr('from')[0])
            if header_from:
                doc.AddItem('&nbsp;&nbsp;<i>' + html_quote(header_from) + '</i>')
            doc.AddItem('</li>\n')
        counter += 1
    doc.AddItem('</ul>\n')
    doc.AddItem('<p>\n<hr>\n<p>\n')
    l = Link(mlist.GetScriptURL('editarch'), _('Back to main overview'))
    doc.AddItem(l)

# Display list of months containing messages in the archive
def DisplayMonthOverview(mlist, mbox, doc):
    counter = 1
    inc = 100
    lastend = 0
    firstcounter = counter
    firstdate = time.localtime(0)
    lastdate = time.localtime()
    monthlist = [ ]
    while 1:
        try:
            m = mbox.next()
        except Errors.DiscardMessage:
            continue
        if m is None:
            monthlist.append(lastdate[:2])
            break

        date = GetDate(m)

        lastyear = lastdate[0]
        lastmonth = lastdate[1]
        thisyear = date[0]
        thismonth = date[1]

        if counter != 1 and thismonth != lastmonth or thisyear != lastyear:
            monthlist.append(lastdate[:2])

        counter += 1
        lastdate = date

    if counter == 1:
        doc.AddItem(_('No messages in archive.\n<p>\n'))
        return

    monthlist.sort()
    monthlist = RemoveDuplicates(monthlist)
    monthlist.reverse()

    links = UnorderedList()
    for date in monthlist:
        l = Link(mlist.GetScriptURL('editarch') + '/box/' + str(date[0]) + '/' + str(date[1]), MakeDateString(date[0], date[1]))
        links.AddItem(l)
    doc.AddItem(links)

# Delete a message by message number, locking the list while doing so
def DeleteMessage(mlist, mbox, msg_num, wname, doc):
    # Unlocking method from Mailman/Cgi/admin.py
    def sigterm_handler(signum, frame, mlist=mlist):
        # Make sure the list gets unlocked...
        mlist.Unlock()
        # ...and ensure we exit, otherwise race conditions could cause us to
        # enter MailList.Save() while we're in the unlocked state, and that
        # could be bad!
        sys.exit(0)

    # Lock the list for good measure
    omask = os.umask(002)
    mlist.Lock()
    try:
        signal.signal(signal.SIGTERM, sigterm_handler)

        # Lock the archives while working
        lock_file = None
        lock_file = LockFile.LockFile(
            os.path.join(mm_cfg.LOCK_DIR,
                         mlist.internal_name() + '.archiver.lock'), lifetime=3*60)
        try:
            lock_file.lock(timeout=0.5)
        except LockFile.AlreadyLockedError:
            doc.AddItem('Couldn\'t lock the archives.  Try again in a few minutes.')
            doc.AddItem(mlist.GetMailmanFooter())
            print doc.Format()
            sys.exit(0)
        except LockFile.TimeOutError:
            doc.AddItem('Couldn\'t lock the archives.  Try again in a few minutes.')
            doc.AddItem(mlist.GetMailmanFooter())
            print doc.Format()
            sys.exit(0)

        warchfile = file(wname, 'w')

        counter = 1
        while 1:
            try:
                m = mbox.next()
            except Errors.DiscardMessage:
                continue
            if m is None:
                break
            if counter != msg_num:
                warchfile.write(m.unixfrom)
                for l in m.headers:
                    warchfile.write(l)
                warchfile.write('\n')
                warchfile.write(m.fp.read())
            counter += 1

        if lock_file:
            lock_file.unlock(unconditionally=1)

    finally:
        mlist.Unlock()
        os.umask(omask)

# Add the listname to the file of archives to be reprocessed
def TagForArchProcessing(mlist):
    fp = open(mm_cfg.EDITED_ARCHIVES_FILE, 'a')
    fp.write(mlist.internal_name() + '\n')
    fp.close()

# Get the date of a message by message number
def GetMessageDate(mbox, msg_num):
    counter = 1
    while 1:
        m = mbox.next()
        if m is None:
            return None
        if counter == msg_num:
            return GetDate(m)
        counter += 1
    return

# Get the date of a given message
def GetDate(m):
    date = floatdate('date', m)
    if date is None:
        date = floatdate('x-list-received-date', m)
    if date is None:
        date = time.localtime()

    # if the year is two digits since the epoch, make it four
    # (some messages show up in pipermail as being from 1969, so 68 is
    #  the cutoff)
    if date[0] > 68 and date[0] < 100:
        tempdatelist = list(date)
        tempdatelist[0] += 1900
        date = tuple(tempdatelist)

    # if the year is still screwy, set the date to now
    if date[0] < 1969:
        date = time.localtime()

    return date

def floatdate(header, message):
    missing = []
    datestr = message.get(header, missing)
    if datestr is missing:
        return None
    date = parsedate_tz(datestr)
    return date

# Make a human-readable Month YYYY from month and year numbers
def MakeDateString(year, month):
    try:
        date = time.strptime(str(year) + " " + str(month), "%Y %m")
        datestr = _(time.strftime("%B %Y", date))
        return datestr
    except ValueError:
        return ''

# Remove duplicates from a sorted list
def RemoveDuplicates(list):
    n = len(list)
    last = list[0]
    i = 1
    lasti = 1
    while i < n:
        if list[i] != last:
            list[lasti] = list[i]
            last = list[i]
            lasti += 1
        i += 1
    return list[:lasti]

# body decoding adapted from email Message
def decode_body(m, field):
    cte = m.get('content-transfer-encoding', '').lower()
    if cte == 'quoted-printable':
        return _qdecode(field)
    elif cte == 'base64':
        try:
            return _bdecode(field)
        except binascii.Error:
            # Incorrect padding
            return field
    elif cte in ('x-uuencode', 'uuencode', 'uue', 'x-uue'):
        sfp = StringIO()
        try:
            uu.decode(StringIO(field+'\n'), sfp)
            field = sfp.getvalue()
        except uu.Error:
            # Some decoding problem
            return field
    return field

# header decoding adapted from Archiver/HyperArch.py
def decode(field):
    if field is None:
        return field
    decoded_field = decode_charset(field)
    if decoded_field:
        field = decoded_field
    return field

def decode_charset(field):
    if field.find("=?") == -1:
        return None
    # Get the decoded header as a list of (s, charset) tuples
    pairs = decode_header(field)
    # Use __unicode__() until we can guarantee Python 2.2
    try:
        # Use a large number for maxlinelen so it won't get wrapped
        h = make_header(pairs, 99999)
        return h.__unicode__()
    except (UnicodeError, LookupError):
        # Unknown encoding
        return None
    # The last value for c will have the proper charset in it
    return EMPTYSTRING.join([s for s, c in pairs])

# from Archiver/HyperArch.py
def html_quote(s, lang=None):
    if s is None:
        return ''
    repls = ( ('&', '&amp;'),
              ("<", '&lt;'),
              (">", '&gt;'),
              ('"', '&quot;'))
    for thing, repl in repls:
        s = s.replace(thing, repl)
    return Utils.uncanonstr(s, lang)
