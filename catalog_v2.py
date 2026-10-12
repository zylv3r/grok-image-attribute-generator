"""Validated active catalog and lossless, reviewable legacy draft migration.

This module only reads catalog data.  It does not publish previews, read provider
configuration, or change archived presets and gallery selection vocabularies.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re


_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_CONTROLS = {"swatch", "range", "select", "cards"}
_DISPOSITIONS = {"keep", "move", "disclosed_recipe", "retire_unresolved"}


def _attributes(library):
    return {a["id"]: a for c in library["categories"] for a in c["attributes"]}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _identifier(value, label):
    _require(isinstance(value, str) and bool(_ID.fullmatch(value)), f"invalid {label} ID: {value!r}")


def _text(value, label):
    _require(isinstance(value, str) and bool(value.strip()), f"missing {label}")


def _reference_map(mapping, attrs, label, allow_empty=False):
    _require(isinstance(mapping, dict), f"{label} must be an object")
    for aid, ids in mapping.items():
        _require(aid in attrs, f"unknown {label} attribute: {aid}")
        _require(isinstance(ids, list) and (bool(ids) or allow_empty), f"{label}.{aid} must contain value IDs")
        _require(all(isinstance(v, str) for v in ids), f"invalid {label}.{aid} value IDs")
        _require(len(ids) == len(set(ids)), f"duplicate {label}.{aid} value IDs")
        known = {v["id"] for v in attrs[aid]["values"]}
        for vid in ids:
            _require(vid in known, f"unknown {label} reference: {aid}:{vid}")


def validate_library(library):
    """Reject malformed v2 controls and dangling executable references."""
    _require(isinstance(library, dict), "library must be an object")
    categories = library.get("categories")
    _require(isinstance(categories, list) and bool(categories), "library categories must be a nonempty array")
    category_ids, attribute_ids = set(), set()
    for category in categories:
        _require(isinstance(category, dict), "category must be an object")
        cid = category.get("id")
        _identifier(cid, "category")
        _require(cid not in category_ids, f"duplicate category ID: {cid}")
        category_ids.add(cid)
        _text(category.get("name"), f"category {cid} name")
        attrs = category.get("attributes")
        _require(isinstance(attrs, list) and bool(attrs), f"category {cid} attributes must be a nonempty array")
        for attr in attrs:
            _require(isinstance(attr, dict), f"category {cid} attribute must be an object")
            aid = attr.get("id")
            _identifier(aid, "attribute")
            _require(aid not in attribute_ids, f"duplicate attribute ID: {aid}")
            attribute_ids.add(aid)
            _text(attr.get("name"), f"attribute {aid} name")
            _text(attr.get("description"), f"attribute {aid} description")
            _require(isinstance(attr.get("type"), str) and attr["type"] in {"exclusive", "multi", "boolean"},
                     f"invalid attribute type: {aid}")
            _require(isinstance(attr.get("control"), str) and attr["control"] in _CONTROLS, f"invalid control: {aid}")
            for key in ("preview_method", "preview_scope", "comparison_group"):
                _text(attr.get(key), f"attribute {aid} {key}")
            values = attr.get("values")
            _require(isinstance(values, list) and bool(values), f"attribute {aid} values must be a nonempty array")
            value_ids = set()
            for value in values:
                _require(isinstance(value, dict), f"attribute {aid} value must be an object")
                vid = value.get("id")
                _identifier(vid, "value")
                _require(vid not in value_ids, f"duplicate value ID: {aid}:{vid}")
                value_ids.add(vid)
                for key in ("name", "description", "steers"):
                    _text(value.get(key), f"value {aid}:{vid} {key}")
                # Publication is represented only by registered comparison assets.
                thumb = value.get("thumbnail", "")
                _require(not thumb or (isinstance(thumb, str) and not thumb.startswith("/api/comparisons/")),
                         f"unreviewed controlled thumbnail: {aid}:{vid}")
                if attr["preview_method"] == "control_only":
                    _require(not thumb, f"control-only value has a thumbnail: {aid}:{vid}")
                if attr["control"] == "swatch":
                    swatch = value.get("swatch")
                    _require(isinstance(swatch, dict), f"missing RGB swatch: {aid}:{vid}")
                    rgb = swatch.get("rgb")
                    _require(isinstance(rgb, list) and len(rgb) == 3
                             and all(isinstance(n, int) and not isinstance(n, bool) and 0 <= n <= 255 for n in rgb),
                             f"invalid RGB swatch: {aid}:{vid}")
                    _text(swatch.get("texture"), f"swatch {aid}:{vid} texture")
            if attr["preview_method"] == "control_only" or attr["control"] == "swatch":
                _require(attr.get("provider_allowed") is False, f"provider must be disabled for {aid}")
            if "default" in attr:
                _require(isinstance(attr["default"], str) and attr["default"] in value_ids,
                         f"unknown default: {aid}:{attr['default']}")
            if attr["control"] == "range":
                spec = attr.get("range")
                _require(attr["type"] == "exclusive" and isinstance(spec, dict), f"invalid range control: {aid}")
                _require(set(spec) == {"min", "max", "step"}, f"invalid range keys: {aid}")
                _require(all(isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n)
                             for n in spec.values()), f"invalid range numbers: {aid}")
                _require(spec["min"] < spec["max"] and spec["step"] > 0, f"invalid range bounds: {aid}")

    attrs = _attributes(library)
    known = {f"{aid}:{v['id']}" for aid, attr in attrs.items() for v in attr["values"]}
    for aid, attr in attrs.items():
        for value in attr["values"]:
            label = f"{aid}:{value['id']}"
            exclusions = value.get("excludes", [])
            _require(isinstance(exclusions, list), f"invalid excludes: {label}")
            for ref in exclusions:
                _require(isinstance(ref, str) and ref in known, f"unknown excludes reference: {ref}")
                _require(ref != label, f"self exclusion: {label}")
            if "recipe" in value:
                recipe = value["recipe"]
                _require(isinstance(recipe, dict), f"invalid recipe: {label}")
                selections = recipe.get("selections")
                _reference_map(selections, attrs, f"recipe {label}")
                _require(bool(selections), f"empty recipe: {label}")
                allowed = recipe.get("allowed_component_changes")
                _require(isinstance(allowed, list) and all(isinstance(a, str) and a in attrs for a in allowed),
                         f"unknown recipe allowed component changes: {label}")
                _require(len(allowed) == len(set(allowed)), f"duplicate recipe allowed component: {label}")
                _require(set(selections) <= set(allowed), f"recipe changes undeclared component: {label}")
                _require(aid not in selections, f"self-referential recipe: {label}")
                for target_aid, ids in selections.items():
                    _require(attrs[target_aid]["type"] == "multi" or len(ids) <= 1,
                             f"recipe sets multiple exclusive values: {label} -> {target_aid}")
    rules = library.get("compatibility_rules", [])
    _require(isinstance(rules, list), "compatibility_rules must be an array")
    rule_ids = set()
    for rule in rules:
        _require(isinstance(rule, dict), "compatibility rule must be an object")
        rid = rule.get("id")
        _identifier(rid, "rule")
        _require(rid not in rule_ids, f"duplicate compatibility rule ID: {rid}")
        rule_ids.add(rid)
        _text(rule.get("message"), f"rule {rid} message")
        _reference_map(rule.get("when"), attrs, f"rule {rid} when")
        _require(bool(rule["when"]), f"rule {rid} has no trigger")
        _require(bool(rule.get("requires") or rule.get("excludes")), f"rule {rid} has no constraint")
        for key in ("requires", "excludes", "unless"):
            if key in rule:
                _reference_map(rule[key], attrs, f"rule {rid} {key}")
    # Recipes may nest, but a cycle cannot be expanded or interpreted safely.
    recipes = {f"{aid}:{v['id']}": v["recipe"]["selections"] for aid, a in attrs.items()
               for v in a["values"] if "recipe" in v}
    visited, visiting = set(), set()
    def visit(key):
        _require(key not in visiting, f"cyclic recipe: {key}")
        if key in visited:
            return
        visiting.add(key)
        for target_aid, ids in recipes[key].items():
            for vid in ids:
                child = f"{target_aid}:{vid}"
                if child in recipes:
                    visit(child)
        visiting.remove(key)
        visited.add(key)
    for key in recipes:
        visit(key)
    return None


def _read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result, f"duplicate JSON key in {path.name}: {key}")
            result[key] = value
        return result
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                          parse_constant=lambda token: (_ for _ in ()).throw(ValueError(f"invalid JSON number: {token}")))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load catalog file {path}: {exc}") from exc


def load_bundle(root):
    """Read v2 only when activated; custom legacy roots retain their old behavior."""
    root = Path(root)
    folder = root / "catalog" / "v2"
    if not (folder / "library.json").is_file():
        return None
    library = _read_json(folder / "library.json")
    validate_library(library)
    legacy = _read_json(root / "catalog" / "v1" / "library.json")
    aliases = _read_json(folder / "aliases.json")
    retired = _read_json(folder / "retired.json")
    coverage = _read_json(folder / "coverage.json")
    activation = _read_json(folder / "active.json")
    _require(isinstance(aliases, dict), "aliases must be an object")
    _require(isinstance(retired, dict) and isinstance(retired.get("attributes"), dict)
             and isinstance(retired.get("values"), dict), "retired ledger must contain attributes and values")
    _require(isinstance(coverage, dict), "coverage must be an object")
    owners = coverage.get("attributes", coverage.get("coverage"))
    _require(isinstance(owners, dict), "coverage must contain attribute owners")
    old_attrs, active_attrs = _attributes(legacy), _attributes(library)
    old_values = {f"{aid}:{v['id']}": v for aid, a in old_attrs.items() for v in a["values"]}
    old_pairs = {f"{aid}:{v['id']}" for aid, a in old_attrs.items() for v in a["values"]}
    _require(set(aliases) == old_pairs, "alias ledger must account for every legacy value exactly once")
    _require(set(owners) == set(old_attrs), "coverage must account for every legacy attribute exactly once")
    categories = {c["id"] for c in library["categories"]}
    for aid, owner in owners.items():
        _require(isinstance(owner, dict) and isinstance(owner.get("owner_category"), str)
                 and owner["owner_category"] in categories,
                 f"invalid coverage owner: {aid}")
    for key, alias in aliases.items():
        _require(isinstance(alias, dict) and isinstance(alias.get("disposition"), str)
                 and alias["disposition"] in _DISPOSITIONS, f"invalid alias: {key}")
        for label in ("legacy_name", "legacy_steer", "reason"):
            _text(alias.get(label), f"alias {key} {label}")
        _require(alias["legacy_name"] == old_values[key]["name"]
                 and alias["legacy_steer"] == old_values[key]["steers"], f"alias changes archived wording: {key}")
        if "legacy_description" in alias:
            _require(alias["legacy_description"] == old_values[key]["description"], f"alias changes archived description: {key}")
        targets = alias.get("targets")
        _require(isinstance(targets, list), f"alias targets must be an array: {key}")
        _require(bool(targets) == (alias["disposition"] != "retire_unresolved"), f"invalid alias disposition targets: {key}")
        seen = set()
        for target in targets:
            _require(isinstance(target, dict), f"invalid alias target: {key}")
            aid, vid = target.get("attribute_id"), target.get("value_id")
            _require(isinstance(aid, str) and isinstance(vid, str) and aid in active_attrs
                     and vid in {v["id"] for v in active_attrs[aid]["values"]},
                     f"unknown alias target: {key} -> {aid}:{vid}")
            _require((aid, vid) not in seen, f"duplicate alias target: {key}")
            seen.add((aid, vid))
        if alias["disposition"] == "keep":
            _require(seen == {tuple(key.split(":"))}, f"keep alias changes identity: {key}")
    for key, expected in (("legacy_attribute_count", len(old_attrs)), ("legacy_value_count", len(old_pairs))):
        _require(type(coverage.get(key)) is int and coverage[key] == expected, f"incorrect coverage {key}")
    frozen_bytes = (root / "catalog" / "v1" / "library.json").read_bytes()
    _require(coverage.get("v1_sha256") == hashlib.sha256(frozen_bytes).hexdigest(), "coverage v1 hash differs from frozen archive")
    if (root / "library.json").is_file():
        _require((root / "library.json").read_bytes() == frozen_bytes, "root v1 library differs from frozen archive")
    retired_values = {key for key, alias in aliases.items() if alias["disposition"] == "retire_unresolved"}
    _require(set(retired["values"]) == retired_values, "retired values must exactly match unresolved alias dispositions")
    for key in retired_values:
        _require(retired["values"][key] == aliases[key], f"retired value differs from its archived alias: {key}")
    retired_attributes = set(old_attrs) - set(active_attrs)
    _require(set(retired["attributes"]) == retired_attributes, "retired attribute ledger is incomplete or has unexpected controls")
    active_owners = {a["id"]: c["id"] for c in library["categories"] for a in c["attributes"]}
    for aid, old_attr in old_attrs.items():
        dispositions = {v["id"]: aliases[f"{aid}:{v['id']}"]["disposition"] for v in old_attr["values"]}
        unique = set(dispositions.values())
        disposition = next(iter(unique)) if len(unique) == 1 else "mixed"
        _require(owners[aid].get("disposition") == disposition, f"incorrect attribute disposition: {aid}")
        _require(owners[aid].get("value_dispositions") == dispositions, f"incorrect value dispositions: {aid}")
        if aid in active_attrs:
            _require(owners[aid]["owner_category"] == active_owners[aid], f"coverage owner disagrees with active category: {aid}")
        else:
            row = retired["attributes"][aid]
            _require(isinstance(row, dict), f"invalid retired attribute: {aid}")
            _require(row.get("legacy_name") == old_attr["name"] and row.get("legacy_description") == old_attr["description"],
                     f"retired attribute changes archived wording: {aid}")
            _require(row.get("owner_category") == owners[aid]["owner_category"], f"retired attribute owner disagrees with coverage: {aid}")
            expected = "retire_unresolved" if unique == {"retire_unresolved"} else "reconciled"
            _require(row.get("disposition") == expected, f"incorrect retired attribute disposition: {aid}")
    expected_counts = {c["id"]: {"attributes": len(c["attributes"]),
                       "values": sum(len(a["values"]) for a in c["attributes"])} for c in library["categories"]}
    _require(coverage.get("active_counts") == expected_counts, "coverage active counts disagree with library")
    _require(isinstance(activation, dict) and activation.get("version") == 2, "invalid catalog activation version")
    pointers = activation.get("categories")
    _require(isinstance(pointers, dict) and set(pointers) == categories, "catalog activation must cover each active category")
    for cid, pointer in pointers.items():
        _require(isinstance(pointer, dict), f"invalid category activation: {cid}")
        _require(pointer.get("controls") == {"version": 2, "source": "catalog/v2/library.json", "status": "active"},
                 f"invalid active controls pointer: {cid}")
        # This catalog activates controls only. Controlled publications live in
        # the operator-approved comparison registry, not a fabricated pointer.
        _require(pointer.get("comparison_previews") == {"status": "awaiting_operator_review", "source": None},
                 f"catalog comparison previews require operator review: {cid}")
        _require(pointer.get("previous") == {"version": 1, "source": "catalog/v1/library.json"},
                 f"invalid frozen rollback pointer: {cid}")
    return {"library": library, "legacy_library": legacy, "aliases": aliases,
            "retired": retired, "coverage": coverage}


def historical_library(bundle):
    """Union active and frozen legacy IDs for gallery filters, never generation."""
    result = deepcopy(bundle["library"])
    attrs = _attributes(result)
    categories = {c["id"]: c for c in result["categories"]}
    for category in bundle["legacy_library"]["categories"]:
        for old_attr in category["attributes"]:
            aid = old_attr["id"]
            if aid in attrs:
                known = {v["id"] for v in attrs[aid]["values"]}
                attrs[aid]["values"].extend(deepcopy(v) for v in old_attr["values"] if v["id"] not in known)
            else:
                cid = category["id"]
                if cid not in categories:
                    categories[cid] = {k: deepcopy(v) for k, v in category.items() if k != "attributes"}
                    categories[cid]["attributes"] = []
                    result["categories"].append(categories[cid])
                archived = deepcopy(old_attr)
                archived["historical_only"] = True
                categories[cid]["attributes"].append(archived)
                attrs[aid] = archived
    result["historical_vocabulary"] = True
    return result


def validate_compatibility(selections, library):
    """Evaluate simultaneous selections, not a union of independent vary pools."""
    if not isinstance(selections, dict):
        return "selections must be an object"
    attrs = _attributes(library)
    selected = {}
    for aid, ids in selections.items():
        if aid not in attrs:
            return f"unknown attribute: {aid}"
        if not isinstance(ids, list) or any(not isinstance(v, str) for v in ids):
            return f"{aid} must contain an array of value IDs"
        if len(ids) != len(set(ids)):
            return f"{aid} contains duplicate value IDs"
        known = {v["id"] for v in attrs[aid]["values"]}
        for vid in ids:
            if vid not in known:
                return f"unknown value: {aid}:{vid}"
        if attrs[aid]["type"] in {"exclusive", "boolean"} and len(ids) > 1:
            return f"{aid} permits at most one {attrs[aid]['type']} value"
        selected[aid] = set(ids)
    indexed_values = {aid: {v["id"]: v for v in attr["values"]} for aid, attr in attrs.items()}
    # Apply recipe components to an evaluation copy so their underlying rules
    # also execute. This never edits the caller's selections or prompt snapshot.
    queue = [(aid, vid) for aid, ids in selected.items() for vid in sorted(ids)]
    evaluated = set()
    while queue:
        aid, vid = queue.pop(0)
        if (aid, vid) in evaluated:
            continue
        evaluated.add((aid, vid))
        value = indexed_values[aid][vid]
        for component, wanted in value.get("recipe", {}).get("selections", {}).items():
            actual = selected.get(component, set())
            if actual and not actual <= set(wanted):
                return f"recipe {aid}:{vid} conflicts with explicit {component}: {', '.join(sorted(actual))}"
            if not actual:
                selected[component] = set(wanted)
                queue.extend((component, v) for v in wanted)
    for aid, ids in selected.items():
        for vid in sorted(ids):
            for ref in indexed_values[aid][vid].get("excludes", []):
                target_aid, target_vid = ref.split(":", 1)
                if target_vid in selected.get(target_aid, set()):
                    return f"conflicting selections: {aid}:{vid} excludes {ref}"
    def matches(mapping):
        return all(bool(selected.get(aid, set()) & set(ids)) for aid, ids in mapping.items())
    for rule in library.get("compatibility_rules", []):
        if not matches(rule["when"]):
            continue
        if rule.get("unless") and matches(rule["unless"]):
            continue
        for aid, ids in rule.get("requires", {}).items():
            if not selected.get(aid, set()) & set(ids):
                return rule["message"]
        for aid, ids in rule.get("excludes", {}).items():
            found = selected.get(aid, set()) & set(ids)
            if found:
                return rule["message"]
    return None


def resolve_draft(raw, bundle):
    """Return a migration preview without destroying unsupported saved fields.

    Alias transactions are atomic: a recipe with a conflicting explicit target
    applies none of its components. Unknown values stay visible in the returned
    draft and are separately reported for an Apply-known-controls decision.
    """
    if not isinstance(raw, dict):
        raise ValueError("draft must be an object")
    draft = deepcopy(raw)
    changes, unresolved = [], []
    attrs = _attributes(bundle["library"])
    values = {aid: {v["id"]: v for v in a["values"]} for aid, a in attrs.items()}
    aliases = bundle["aliases"]
    migrated_attrs = {}

    def problem(field, aid, vid, reason, **extra):
        unresolved.append(dict(field=field, attribute_id=aid, value_id=vid, reason=reason, **extra))

    def migration_priority(aid, vid):
        alias = aliases.get(f"{aid}:{vid}")
        if alias and alias["disposition"] not in {"keep", "retire_unresolved"}:
            recipe_target = any("recipe" in values.get(t["attribute_id"], {}).get(t["value_id"], {})
                                for t in alias["targets"])
            return int(alias["disposition"] == "disclosed_recipe" or len(alias["targets"]) > 1 or recipe_target)
        return int(aid in values and vid in values[aid] and "recipe" in values[aid][vid])

    def expanded_targets(targets):
        # Retain the canonical recipe selector as well as disclosing all of its
        # implied components. Nested expansion is one atomic migration, so deep
        # conflicts cannot leave an intermediate recipe-only draft behind.
        queue, expanded, seen = list(targets), [], set()
        while queue:
            target = queue.pop(0)
            aid, vid = target["attribute_id"], target["value_id"]
            if (aid, vid) in seen:
                continue
            seen.add((aid, vid))
            expanded.append(deepcopy(target))
            recipe = values.get(aid, {}).get(vid, {}).get("recipe", {})
            queue.extend({"attribute_id": component, "value_id": value}
                         for component, ids in recipe.get("selections", {}).items() for value in ids)
        return expanded

    def attribute_priority(item):
        aid, ids = item
        if not isinstance(ids, list) or any(not isinstance(v, str) for v in ids):
            return 0
        return max((migration_priority(aid, vid) for vid in ids), default=0)

    for field in ("selections", "whitelist"):
        if field not in raw:
            continue
        source = raw.get(field, {})
        if not isinstance(source, dict):
            problem(field, None, None, f"unsupported {field} structure", raw=deepcopy(source))
            continue
        output = draft.setdefault(field, {})
        # Canonicalize independent aliases before evaluating coupled recipes.
        # An equivalent explicit legacy target must not depend on JSON key order.
        for aid, ids in sorted(source.items(), key=attribute_priority):
            if not isinstance(ids, list) or any(not isinstance(v, str) for v in ids):
                problem(field, aid, None, "unsupported value ID array", raw=deepcopy(ids))
                continue
            if not ids and aid not in attrs:
                problem(field, aid, None, "unknown or retired attribute")
            for vid in sorted(ids, key=lambda value: migration_priority(aid, value)):
                alias = aliases.get(f"{aid}:{vid}")
                retain_source = False
                if alias and alias["disposition"] == "retire_unresolved":
                    problem(field, aid, vid, alias.get("reason", "retired without a semantic equivalent"))
                    continue
                if alias and alias["disposition"] != "keep":
                    targets = alias["targets"]
                    disposition = alias["disposition"]
                elif aid in values and vid in values[aid]:
                    recipe = values[aid][vid].get("recipe")
                    if not recipe:
                        continue
                    targets = [{"attribute_id": target, "value_id": value}
                               for target, wanted in recipe["selections"].items() for value in wanted]
                    disposition, retain_source = "disclosed_recipe", True
                else:
                    problem(field, aid, vid, "unknown attribute or value; raw selection preserved")
                    continue
                targets = expanded_targets(targets)
                target_attrs = {t["attribute_id"] for t in targets}
                if field == "whitelist" and len(target_attrs) > 1:
                    problem(field, aid, vid, "coupled recipe cannot become independent variation pools", targets=deepcopy(targets))
                    continue
                candidate = deepcopy(output)
                replacement_position = None
                if not retain_source:
                    if vid in candidate.get(aid, []):
                        replacement_position = candidate[aid].index(vid)
                    candidate[aid] = [v for v in candidate.get(aid, []) if v != vid]
                    if not candidate[aid] and aid not in attrs:
                        del candidate[aid]
                conflict = None
                for target in targets:
                    target_aid, target_vid = target["attribute_id"], target["value_id"]
                    current = candidate.get(target_aid, [])
                    if not isinstance(current, list) or any(not isinstance(v, str) for v in current):
                        conflict = f"target {target_aid} has unsupported raw structure"
                        break
                    opposite = raw.get("whitelist" if field == "selections" else "selections", {})
                    if target_aid != aid and isinstance(opposite, dict) and target_aid in opposite and opposite[target_aid]:
                        conflict = f"target {target_aid} is explicitly controlled in the other selection mode"
                        break
                    explicit_modes = raw.get("attributeModes", {})
                    if target_aid != aid and isinstance(explicit_modes, dict) and target_aid in explicit_modes and explicit_modes[target_aid] != field:
                        conflict = f"target {target_aid} has an explicit incompatible attribute mode"
                        break
                    if field == "selections" and attrs[target_aid]["type"] != "multi" and current and current != [target_vid]:
                        conflict = f"recipe or alias conflicts with explicit {target_aid}: {', '.join(current)}"
                        break
                    if target_vid not in current:
                        target_values = candidate.setdefault(target_aid, [])
                        if target_aid == aid and replacement_position is not None:
                            target_values.insert(replacement_position, target_vid)
                            replacement_position += 1
                        else:
                            target_values.append(target_vid)
                if not conflict and field == "selections":
                    # Validate only supported controls; retained unresolved controls
                    # must not prevent independent valid migrations.
                    known_candidate = {a: vs for a, vs in candidate.items() if a in values and isinstance(vs, list)
                                       and all(isinstance(v, str) and v in values[a] for v in vs)}
                    conflict = validate_compatibility(known_candidate, bundle["library"])
                if conflict:
                    problem(field, aid, vid, conflict, targets=deepcopy(targets))
                    continue
                if candidate == output:
                    continue
                output.clear()
                output.update(candidate)
                changes.append(dict(field=field, attribute_id=aid, value_id=vid,
                                    disposition=disposition, targets=deepcopy(targets)))
                migrated_attrs.setdefault(aid, set()).update(target_attrs)
    modes = raw.get("attributeModes")
    if modes is not None:
        if not isinstance(modes, dict):
            problem("attributeModes", None, None, "unsupported attributeModes structure", raw=deepcopy(modes))
        else:
            for aid, mode in modes.items():
                if not isinstance(mode, str) or mode not in {"selections", "whitelist"}:
                    problem("attributeModes", aid, None, "unsupported attribute mode", raw=deepcopy(mode))
                    continue
                if aid in attrs:
                    continue
                targets = migrated_attrs.get(aid, set())
                if not targets or any(u["attribute_id"] == aid for u in unresolved):
                    problem("attributeModes", aid, None, "unknown or unresolved attribute mode preserved")
                    continue
                conflicts = [a for a in targets if a in modes and modes[a] != mode]
                if conflicts:
                    problem("attributeModes", aid, None, f"conflicting target modes: {', '.join(sorted(conflicts))}")
                    continue
                for target in targets:
                    draft["attributeModes"].setdefault(target, mode)
                del draft["attributeModes"][aid]
    return {"draft": draft, "changes": changes, "unresolved": unresolved}
