"""Boundaries for the single-user, loopback-only application (not deployment auth)."""
import ipaddress


def is_local_client(host):
    if host == 'testclient':  # Starlette's in-process test transport, never a TCP peer.
        return True
    try:
        address = ipaddress.ip_address(host)
        return address.is_loopback or bool(getattr(address, 'ipv4_mapped', None) and address.ipv4_mapped.is_loopback)
    except (ValueError, TypeError):
        return False


def forbidden_browser_request(request, origins):
    origin = request.headers.get('origin')
    if origin is not None and origin not in origins:
        return True
    # Cross-site navigations/subresources can omit Origin. OAuth's top-level GET
    # is allowed through to its separate single-use browser/state validation.
    callback = request.method == 'GET' and request.url.path == '/api/v1/social/meta/callback'
    return (request.url.path.startswith('/api/') and not callback and origin is None
            and request.headers.get('sec-fetch-site') == 'cross-site')


def protect_response(request, response):
    response.headers['X-Request-ID'] = request.state.request_id
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    policy = "frame-ancestors 'none'; base-uri 'self'; object-src 'none'"
    # Framework documentation uses its own CDN/inline scripts; the SPA needs
    # only bundled scripts, local API calls and local/data/blob poster images.
    if (response.headers.get('content-type', '').startswith('text/html')
            and request.url.path not in {'/docs', '/redoc', '/docs/oauth2-redirect'}):
        policy += ("; default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'"
                   "; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'"
                   "; frame-src 'none'; form-action 'self'")
    response.headers['Content-Security-Policy'] = policy
    if request.url.path.startswith('/api/'):
        response.headers.setdefault('Cache-Control', 'no-store')
    return response
