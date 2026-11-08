"""Application export presets, not promises of publishing API compatibility."""

PRESETS = {
    'instagram': {'preset_id': 'instagram-portrait-v1', 'name': 'Instagram portrait', 'width': 1080, 'height': 1350},
    'facebook': {'preset_id': 'facebook-square-v1', 'name': 'Facebook square', 'width': 1080, 'height': 1080},
    'linkedin': {'preset_id': 'linkedin-landscape-v1', 'name': 'LinkedIn landscape', 'width': 1200, 'height': 900},
}


def platform_css(platform):
    if platform == 'instagram':
        return '.content { top:90px; bottom:90px; } .label { margin-top:110px; }'
    if platform == 'linkedin':
        return '''.content { inset:48px; } .label { margin-top:28px; }
            .copy { padding-top:20px; } h1 { margin-bottom:22px; }
            .cta { margin-top:16px; margin-bottom:16px; }
            .brand { padding-bottom:12px; }'''
    return ''
