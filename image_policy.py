"""Atelier's pinned image backend. No legacy-model fallback or client override."""
IMAGE_MODEL = 'grok-imagine-image-2.0'

def image_policy():
    return {'generation_model': IMAGE_MODEL, 'reference_edit_model': IMAGE_MODEL,
            'legacy_fallback_allowed': False,
            'reference_required_for_edits': True,
            'persona_selection_is_not_mask_or_publication_approval': True}
