"""Readable text treatment independent of model-created background colors."""


def theme_css(theme, template):
    if theme == 'dark':
        return ''  # Preserve the existing dark rendering for older requests.
    base = '''
        body { color:#0f172a; }
        .shade { background:linear-gradient(90deg,rgba(255,255,255,.98) 0%,rgba(255,255,255,.96) 53%,rgba(255,255,255,.12) 76%,rgba(255,255,255,.03) 100%); }
        .body { color:#243247; }
        .label,.footer { color:#475569; }
    '''
    if template == 'editorial-v1':
        base += '.poster > img { left:36%; width:64%; } .copy,.cta { max-width:600px; }'
    elif template == 'spotlight-v1':
        base += '''
            .shade { background:rgba(255,255,255,.12); }
            .content { background:rgba(255,255,255,.95); border-color:#94a3b8; }
        '''
    elif template == 'bulletin-v1':
        base += '.shade { background:rgba(255,255,255,.05); }'
    return base
