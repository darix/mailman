# Copyright (C) 2002 by the Free Software Foundation, Inc.
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

"""
    confirm <confirmation-string>
        Confirm an action.  The confirmation-string is required and should be
        supplied with in mailback confirmation notice.
"""

from Mailman import mm_cfg
from Mailman import Errors
from Mailman import Pending
from Mailman.i18n import _

STOP = 1



def gethelp(mlist):
    return _(__doc__)



def process(res, args):
    mlist = res.mlist
    if len(args) <> 1:
        res.results.append(_('Usage:'))
        res.results.append(gethelp(mlist))
        return STOP
    cookie = args[0]
    try:
        results = mlist.ProcessConfirmation(cookie, res.msg)
    except Errors.MMBadConfirmation, e:
        # Express in approximate days
        days = int(mm_cfg.PENDING_REQUEST_LIFE / mm_cfg.days(1) + 0.5)
        res.results.append(_("""\
Invalid confirmation string.  Note that confirmation strings expire
approximately %(days)s days after the initial subscription request.  If your
confirmation has expired, please try to re-submit your original request or
message."""))
    except Errors.MMNeedApproval:
        res.results.append(_("""\
Your request has been forwarded to the list moderator for approval."""))
    except Errors.MMAlreadyAMember:
        # Some other subscription request for this address has
        # already succeeded.
        res.results.append(_('You are already subscribed.'))
    except Errors.NotAMemberError:
        # They've already been unsubscribed
        res.results.append(_("""\
You are not current a member.  Have you already unsubscribed or changed
your email address?"""))
    else:
        if ((results[0] == Pending.SUBSCRIPTION and mlist.send_welcome_msg)
            or
            (results[0] == Pending.UNSUBSCRIPTION and mlist.send_goodbye_msg)):
            # We don't also need to send a confirmation succeeded message
            res.respond = 0
        else:
            res.results.append(_('Confirmation succeeded'))
            # Consume any other confirmation strings with the same cookie so
            # the user doesn't get a misleading "unprocessed" message.
            match = 'confirm ' + cookie
            unprocessed = []
            for line in res.commands:
                if line.lstrip() == match:
                    continue
                unprocessed.append(line)
            res.commands = unprocessed
    # Process just one confirmation string per message
    return STOP
