# Always-on adult-subject aesthetics

All future Atelier planned generation prompts include the literal words **cute**, **beautiful**, and **gorgeous**. This is a shared server-side direction, not an optional face value that can be left unset. It applies across categories and preserves the existing identity/presentation selections.

`prompt_policy.py` defines the wording. `Catalog.prompt` includes it in the exact authoritative prompt returned by `/api/preview` and persisted with jobs/gallery records. No hidden provider-boundary suffix is added after the saved prompt.

Reference-edit prompts include the same keywords with an explicit restriction: they do not authorize reshaping/beautifying the approved face, changing identity, erasing skin texture or modifying non-target features to pursue the adjectives. The original, reviewed mask and target contract take precedence; explicitly reviewed target consequences remain permitted. The receipt's provider-prompt SHA-256 is computed after the policy is included.

The aesthetic direction remains adult styling with believable anatomy and natural skin texture—not younger age or a demand for exaggerated proportions.

Frozen V1 and active catalog bytes, existing photographs, saved historical prompts, baseline candidates and consumed attempts are unchanged. The previous three baseline candidates were made before this policy; their prompt receipts are not retroactively rewritten. No new images are generated to install/test the policy.

Regression gates:
- Actual catalog prompt plans include all three keywords, including empty, pose, wardrobe, man and nonbinary selections.
- Isolated reference-edit provider capture includes all keywords and the lock restriction; its receipt hashes the exact provider prompt.
- Existing planner tests still assert authoritative selection order and the complete composed prompt.
