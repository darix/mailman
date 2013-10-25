from Mailman import mm_cfg
from Mailman import Utils
from Mailman import MailList

def get_list_attributes_for_overview(script_url_part):
    # Skip any mailing lists that isn't advertised.
    hostname    = Utils.get_domain()
    advertised = []
    listnames = Utils.list_names()
    listnames.sort()

    for name in listnames:
        mlist = MailList.MailList(name, lock=0)
        if mlist.advertised or mm_cfg.OverviewListUnadvertizedMailingLists:
            if mm_cfg.VIRTUAL_HOST_OVERVIEW and (
                   mlist.web_page_url.find('/%s/' % hostname) == -1 and
                   mlist.web_page_url.find('/%s:' % hostname) == -1):
                # List is for different identity of this host - skip it.
                continue
            else:
                if mm_cfg.LISTINFO_USE_CATEGORIES:
                    data = mlist
                else:
                    data = (mlist.GetScriptURL(script_url_part),
                                       mlist.real_name,
                                       mlist.description)
                advertised.append(data)
    return advertised
