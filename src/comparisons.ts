import type { Attribute } from './types';
export type Point = [number, number];
export type ComparisonState = 'draft' | 'contract_approved' | 'pilot_done' | 'pilot_accepted' | 'published';
export type ComparisonBaseline = { asset_id: string; url: string; sha256: string; width: number; height: number; subject_id: string; subject_metadata?: { basis?: string; presentation?: string }; image_id?: string; crop?: unknown };
export type ComparisonMask = { polygon: Point[]; sha256?: string; hash?: string; area?: number };
export type ComparisonArtifact = { id: string; url: string; base_url: string; attribute_id: string; value_id: string; method: string; receipt: Record<string, unknown>; accepted: boolean };
export type ComparisonSummary = { groups?: Record<string, {state: ComparisonState}>; category_id?: string; id?: string; name?: string; state: ComparisonState; contract_hash?: string; artifact_count?: number; baseline?: ComparisonBaseline | null };
export type ComparisonReviewData = { category_id: string; baseline_requirements?: string[]; state: ComparisonState; contract_hash: string; baseline: ComparisonBaseline | null; masks: Record<string, ComparisonMask | Point[]>; artifacts: ComparisonArtifact[]; group?: string | null; cycle?: { id: number; cap: number; used: number }; budget: { cap: number; used: number; cycle_used?: number; cycle_id?: number }; locked_fields: unknown; allowed_changes: unknown; attributes?: Array<Record<string, unknown>>; contract?: Record<string, unknown>; warnings?: string[]; [key: string]: unknown };
export type ComparisonAttribute = Attribute & { preview_method?: string; preview_scope?: string; comparison_group?: string; baseline?: Record<string, unknown>; comparison_baseline?: Record<string, unknown>; preview_contract?: Record<string, unknown> };
export type EditorDraft = { base_sha256?: string; polygon: Point[]; method: string; value: string; params: Record<string, string> };
export function draftKey(category: string, attribute: string) { return `${category}/${attribute}`; }
export function normalizedPoint(x: number, y: number, rect: { left: number; top: number; width: number; height: number }): Point | null {
  if (!(rect.width > 0 && rect.height > 0)) return null;
  return [Math.max(0, Math.min(1, (x - rect.left) / rect.width)), Math.max(0, Math.min(1, (y - rect.top) / rect.height))];
}
export function validPolygon(points: Point[]) {
  if (points.length < 3 || points.some(p => p.length !== 2 || p.some(n => !Number.isFinite(n) || n < 0 || n > 1))) return false;
  if (new Set(points.map(p => p.join(','))).size !== points.length) return false;
  const area = points.reduce((sum, p, i) => { const q = points[(i + 1) % points.length]; return sum + p[0] * q[1] - q[0] * p[1]; }, 0);
  return Math.abs(area) > 1e-8;
}
export function maskPolygon(mask?: ComparisonMask | Point[]): Point[] { return Array.isArray(mask) ? mask : mask?.polygon || []; }
export function isReferenceMethod(method: string) { return method.replaceAll('-', '_') === 'reference_edit'; }
export function previewBlocker(review: ComparisonReviewData, attribute: string, method: string): string | null {
  if (!method || method === 'control_only' || method === 'none') return 'This attribute is a control only; it has no model comparison render.';
  if (!review.baseline && method !== 'fabric_swatch') return 'Choose an owned gallery baseline before previewing.';
  if (review.state === 'published') return 'This category is published. Reopen this review group to revise its comparison contract.';
  if (!isReferenceMethod(method)) return null;
  if (isFabricReference(review.baseline)) return 'Reference edit requires a reviewed adult woman gallery baseline; the fabric reference contains no person.';
  if (review.state === 'draft') return 'Reference edit requires an approved contract.';
  if (!validPolygon(maskPolygon(review.masks[attribute]))) return 'Reference edit requires a saved mask for this attribute.';
  if ((review.cycle?.used ?? review.budget.cycle_used ?? review.budget.used) >= review.budget.cap) return 'The approved category provider budget is exhausted.';
  return null;
}
export function approvalPayload(review: ComparisonReviewData, stage: 'contract' | 'pilot' | 'publish' | 'expansion', artifactIds: string[], cap: number, note: string) {
  if (!Number.isInteger(cap) || cap < 0 || cap > 3) throw Error('Provider attempt cap must be an integer from 0 to 3.');
  if (!review.baseline || !review.contract_hash) throw Error('Choose a baseline and review the current contract first.');
  if (stage === 'contract' && review.state !== 'draft') throw Error('The current category contract has already been approved.');
  if (stage === 'pilot' && !['contract_approved', 'pilot_done', 'pilot_accepted'].includes(review.state)) throw Error('Approve this category contract before accepting candidates.');
  if (stage === 'publish' && review.state !== 'pilot_accepted') throw Error('Publication requires accepted category candidates.');
  if (stage === 'expansion' && !['pilot_accepted','published'].includes(review.state)) throw Error('Accept the previous pilot before approving an expansion cycle.');
  if (stage === 'expansion' && !note.trim()) throw Error('An expansion approval note is required.');
  const selectedArtifactIds = ['pilot','publish'].includes(stage) ? artifactIds : [];
  if (['pilot','publish'].includes(stage) && !artifactIds.length) throw Error('Select at least one reviewed candidate.');
  if (selectedArtifactIds.some(id => !review.artifacts.some(a => a.id === id))) throw Error('All candidates must belong to this category.');
  if (stage === 'publish' && (review.state !== 'pilot_accepted' || artifactIds.some(id => !review.artifacts.some(a => a.id === id && a.accepted)))) throw Error('Publication requires accepted category candidates.');
  return { stage, expected_contract_hash: review.contract_hash, artifact_ids: selectedArtifactIds, provider_attempt_cap: ['contract','expansion'].includes(stage) ? cap : 0, approval_note: note.trim(), ...(review.group ? {group: review.group} : {}) };
}
export function methodLabel(method: string) {
  if (method === 'control_only') return 'Control only · no model render';
  if (isReferenceMethod(method)) return 'Reference-conditioned edit · operator review required';
  if (method.includes('recolor')) return 'Masked photographic recolor · local';
  if (method.includes('swatch')) return 'Textured fabric swatch · local';
  return `Simulated ${method.replace(/^simulated_/, '').replaceAll('_', ' ').replaceAll('-', ' ')} · local`;
}
export function comparisonParameters(method: string, fields: Record<string, string>): Record<string, unknown> {
  const params: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(fields)) {
    if (value === '') continue;
    if (key === 'rgb') {
      if (!/^#[\da-f]{6}$/i.test(value)) throw Error('RGB must be a six-digit hex colour.');
      params.colour = { hex: value.toLowerCase() };
    } else if (['effect', 'focus_target', 'moving_region', 'depth_assumption'].includes(key)) params[key] = value;
    else {
      const n = Number(value);
      if (!Number.isFinite(n)) throw Error(`${key.replaceAll('_', ' ')} must be a finite number.`);
      params[key] = n;
    }
  }
  // method is supplied separately to the API; never encode client state in params.
  void method;
  return params;
}

export function catalogColour(value: unknown): string | null {
  if (!value || typeof value !== 'object') return null;
  const v = value as Record<string, unknown>;
  const colour = v.colour;
  const hex = typeof colour === 'object' && colour ? (colour as Record<string, unknown>).hex : typeof colour === 'string' ? colour : v.hex || v.color;
  if (typeof hex === 'string' && /^#[\da-f]{6}$/i.test(hex)) return hex.toLowerCase();
  if (Array.isArray(v.rgb) && v.rgb.length === 3 && v.rgb.every(n => Number.isInteger(n) && n >= 0 && n <= 255)) return '#' + v.rgb.map(n => n.toString(16).padStart(2, '0')).join('');
  return null;
}

export function isGlobalScope(scope?: string) { return ['global','whole_image','wholeframe','whole_frame'].includes(scope || ''); }
export function parseReview(raw: unknown, categoryId: string, attributeId?: string, group?: string): ComparisonReviewData {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw Error('The server returned an invalid category review. Reload to retry.');
  const r = raw as Record<string, unknown>;
  if (r.baseline_requirements !== undefined && (!Array.isArray(r.baseline_requirements) || !r.baseline_requirements.every(item => typeof item === 'string'))) throw Error('The server returned invalid baseline requirements. Reload to retry.');
  const states = ['draft','contract_approved','pilot_done','pilot_accepted','published'];
  const budget = r.budget as Record<string, unknown> | undefined;
  if (!states.includes(String(r.state)) || typeof r.contract_hash !== 'string' || !/^[a-f0-9]{64}$/.test(r.contract_hash) || !r.masks || typeof r.masks !== 'object' || Array.isArray(r.masks) || !Array.isArray(r.artifacts) || !budget || !Number.isInteger(budget.cap) || !Number.isInteger(budget.used) || Number(budget.cap) < 0 || Number(budget.used) < 0) throw Error('The server returned an invalid category review. Reload to retry.');
  if ((r.category_id && r.category_id !== categoryId) || (r.id && r.id !== categoryId)) throw Error('The category review does not match the selected category. Reload to retry.');
  if (r.baseline !== null) {
    const b = r.baseline as Record<string, unknown> | undefined;
    if (!b || typeof b.url !== 'string' || typeof b.asset_id !== 'string' || !/^[a-f0-9]{32}$/.test(b.asset_id) || typeof b.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(b.sha256) || !(Number(b.width) > 0 && Number(b.height) > 0)) throw Error('The server returned invalid baseline metadata. Reload to retry.');
  }
  if (group && r.group && r.group !== group) throw Error('The review group does not match the selected attribute.');
  if (attributeId && Array.isArray(r.attributes) && !r.attributes.some(a => a && typeof a === 'object' && (a as Record<string, unknown>).id === attributeId)) throw Error('The review group does not contain the selected attribute.');
  return { ...(r as unknown as ComparisonReviewData), category_id: categoryId };
}

export function isFabricReference(baseline: ComparisonBaseline | null) { return baseline?.subject_id === 'fabric-swatch' || baseline?.subject_metadata?.presentation === 'no_person'; }
export function retainedEditorDraft(cached: EditorDraft | undefined, baselineHash?: string): EditorDraft | undefined {
  return cached && cached.base_sha256 === baselineHash ? cached : undefined;
}

export function reopenPayload(review: ComparisonReviewData, note: string) {
  if (!note.trim()) throw Error('A reopen note is required.');
  if (review.state === 'draft') throw Error('This review group is already a draft.');
  return { expected_contract_hash: review.contract_hash, approval_note: note.trim(), ...(review.group ? {group: review.group} : {}) };
}

// The selected server group is authoritative; older reviews can use the catalog declaration.
export function baselineRequirements(review: ComparisonReviewData, attr?: ComparisonAttribute): string[] {
  const requirements = review.baseline_requirements ?? attr?.preview_contract?.baseline_requirements ?? [];
  if (!Array.isArray(requirements) || !requirements.every(item => typeof item === 'string')) throw Error('Invalid baseline requirements. Reload the selected group to retry.');
  return [...requirements];
}
export type BaselinePayload = { image_id: string; subject_id: string; crop?: number[]; baseline_confirmations?: string[] };
export function baselinePayload(imageId: string, crop: number[] | undefined, requirements: string[], confirmed: boolean): BaselinePayload {
  if (requirements.length && !confirmed) throw Error('Confirm the selected group baseline requirements before using this image.');
  return { image_id: imageId, subject_id: 'woman-1', ...(crop ? { crop: [...crop] } : {}), ...(requirements.length ? { baseline_confirmations: [...requirements] } : {}) };
}
