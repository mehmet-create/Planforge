# A context processor runs on every request and injects variables
# into every template automatically — no need to pass them manually from each view.
#
# This one makes two things available in every template:
#   {{ active_org }}  — the organization the user is currently working in
#   {{ user_orgs }}   — all organizations the user belongs to (for the switcher)
#
# Performance note:
# get_active_organization() already uses the session to avoid a DB hit on
# every request (it only queries when the session value is missing or stale).
#
# get_user_organizations() is cached on request.session for 5 minutes so the
# org switcher in the navbar does not add a DB query on every single page load.

from .services import get_active_organization, get_user_organizations
from django.utils import timezone
from django.db.models import Case, IntegerField, When

_ORG_LIST_CACHE_KEY    = "_ctx_user_orgs_ids"
_ORG_LIST_CACHE_TS_KEY = "_ctx_user_orgs_ts"
_ORG_LIST_TTL_SECONDS  = 300   # 5 minutes



def organization_context(request):
    if not request.user.is_authenticated:
        return {
            "active_org": None,
            "user_orgs":  [],
        }

    # get_active_organization() caches its result on request._active_org_cache
    # after the first call (set by the org decorator before the view ran).
    # When we arrive here during template rendering, this is a free attribute
    # lookup — zero DB queries on any page that uses an org decorator.
    active_org = get_active_organization(request)

    # Cache the org list in the session for 5 minutes to avoid a DB query
    # on every page load just to render the org switcher in the navbar.
    # We store org IDs (JSON-serialisable) and a timestamp. When the cache
    # is warm we re-hydrate from the stored IDs in a single IN query.
    # When it expires (or is missing) we do a full re-fetch and repopulate.
    now = timezone.now().timestamp()
    cached_ts  = request.session.get(_ORG_LIST_CACHE_TS_KEY, 0)
    cached_ids = request.session.get(_ORG_LIST_CACHE_KEY)

    if now - cached_ts > _ORG_LIST_TTL_SECONDS or not cached_ids:
        # Cache cold — hit the DB and store IDs + timestamp in session
        user_orgs = list(get_user_organizations(request.user.id))
        request.session[_ORG_LIST_CACHE_KEY]    = [o.id for o in user_orgs]
        request.session[_ORG_LIST_CACHE_TS_KEY] = now
    else:
        # Cache warm — re-fetch only the cached orgs (single IN query, no join)
        
        preserved_order = Case(
            *[When(pk=pk, then=pos) for pos, pk in enumerate(cached_ids)],
            output_field=IntegerField()
        )
        from organizations.models import Organization as Org
        user_orgs = list(Org.objects.filter(pk__in=cached_ids).order_by(preserved_order))

    return {
        "active_org": active_org,
        "user_orgs":  user_orgs,
    }