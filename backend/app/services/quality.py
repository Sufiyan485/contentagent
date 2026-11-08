def check_concept(concept, background, renders, report, platforms=None, exports=None):
    warnings = ['Human review required: source references do not prove every paraphrase is accurate.', 'Visually inspect the background for topic relevance, accidental lettering or watermarks.']
    if report.origin == 'provided':
        warnings.append('User-provided organizational facts are not independently verified; confirm every detail before approval.')
    failures = []
    if platforms:
        exports = exports or {}
        if set(exports) != set(platforms) or any(
            len(exports[p].get('renders', [])) != len(concept.slides) or
            exports[p].get('background_asset_id') != (background.get(p) if isinstance(background,dict) else background)
            for p in platforms if p in exports
        ):
            failures.append('Not every selected platform has a complete export set with the shared background.')
        if {caption.platform for caption in concept.captions} != set(platforms) or len(concept.captions) != len(platforms):
            failures.append('Each selected platform needs exactly one matching caption.')
    if not background or len(renders) != len(concept.slides) * (len(platforms) if platforms else 1):
        failures.append('Not every slide has a rendered poster.')
    known = {c.id for c in report.claims if c.verification_status == 'supported'}
    for part in [*concept.slides,*concept.captions,*[s for v in concept.platform_variants.values() for s in v.slides]]:
        if not part.claim_ids:
            warnings.append('Some content has no factual claim references; review before use.')
        elif not set(part.claim_ids).issubset(known):
            failures.append('Content cites a claim that is not supported by the report.')
    return {'status':'fail' if failures else 'warn','warnings':list(dict.fromkeys(warnings + concept.warnings)),'failures':list(dict.fromkeys(failures)), 'approval_status':'unapproved','publishing_status':'not_published'}
