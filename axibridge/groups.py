"""Hierarchy metadata and coordinate frames; plotting order remains Project.layers."""
import math
from .compose import Affine


def mul(l, r):
    return Affine(a=l.a*r.a+l.c*r.b, b=l.b*r.a+l.d*r.b,
                  c=l.a*r.c+l.c*r.d, d=l.b*r.c+l.d*r.d,
                  e=l.a*r.e+l.c*r.f+l.e, f=l.b*r.e+l.d*r.f+l.f)


def inverse(m):
    det = m.a*m.d-m.b*m.c
    if not all(math.isfinite(v) for v in m.model_dump().values()) or not math.isfinite(det) or abs(det) < 1e-12:
        raise ValueError('placement must be finite and non-singular')
    return Affine(a=m.d/det, b=-m.b/det, c=-m.c/det, d=m.a/det,
                  e=(m.c*m.f-m.d*m.e)/det, f=(m.b*m.e-m.a*m.f)/det)


def group(project, gid):
    for g in project.groups:
        if g.id == gid:
            return g
    raise ValueError(f'unknown group: {gid}')


def chain(project, gid):
    out = []
    while gid:
        if gid in out:
            raise ValueError('group cycle')
        out.append(gid)
        gid = group(project, gid).parent_id
    return list(reversed(out))


def world(project, gid):
    result = Affine()
    for i in chain(project, gid):
        result = mul(result, group(project, i).transform)
    return result


def visible(project, layer):
    return layer.visible and layer.inherited_visible and all(group(project, i).visible and group(project,i).inherited_visible for i in chain(project, layer.group_id))


def descendants(project, gid):
    return [l for l in project.layers if gid in chain(project, l.group_id)]


def target_layers(project, t):
    if t['kind'] == 'group':
        group(project, t['id'])
        return descendants(project, t['id'])
    l = project.layer(t['id'])
    if l.animation_owner_id:
        raise ValueError('select the complete animation family')
    return [k for k in project.layers if k.id == l.id or k.animation_owner_id == l.id]


def normalize(project, targets):
    out = []
    seen = set()
    for t in targets:
        if t.get('kind') not in ('layer', 'group'):
            raise ValueError('invalid selection kind')
        # Validate identity first; family membership is checked after ancestors
        # absorb descendants, including owned animation keys.
        parent(project, t)
        key = (t['kind'], t['id'])
        if key not in seen:
            out.append(dict(t)); seen.add(key)
    selected_groups = {t['id'] for t in out if t['kind'] == 'group'}
    out = [t for t in out if not (set(chain(project, parent(project, t))) & selected_groups)]
    for t in out:
        target_layers(project, t)
    return out


def parent(project, t):
    return group(project, t['id']).parent_id if t['kind'] == 'group' else project.layer(t['id']).group_id


def siblings(project, pid):
    out = []
    seen = set()
    for l in project.layers:
        if l.animation_owner_id:
            continue
        cs = chain(project, l.group_id)
        if pid and pid not in cs:
            continue
        remaining = cs[cs.index(pid)+1:] if pid else cs
        t = {'kind': 'group', 'id': remaining[0]} if remaining else {'kind':'layer', 'id':l.id}
        key = (t['kind'], t['id'])
        if key not in seen:
            seen.add(key); out.append(t)
    return out


def validate_hierarchy(project):
    gids = [g.id for g in project.groups]
    lids = [l.id for l in project.layers]
    if len(lids) != len(set(lids)) or len(gids) != len(set(gids)) or set(gids) & set(lids):
        raise ValueError('duplicate hierarchy id')
    for g in project.groups:
        chain(project, g.id)
        inverse(g.transform)
        ids = [i for i,l in enumerate(project.layers) if g.id in chain(project, l.group_id)]
        if not ids or ids != list(range(min(ids),max(ids)+1)):
            raise ValueError('groups must contain consecutive complete siblings')
    for l in project.layers:
        chain(project, l.group_id)
        if l.animation_owner_id and l.group_id != project.layer(l.animation_owner_id).group_id:
            raise ValueError('split animation family')


def tween_frames(project, layer):
    """Remove common ancestry from references before applying output placement once."""
    own = chain(project, layer.group_id)
    refs = (layer.source.params or {}).get('keys') or [(layer.source.params or {}).get('a'), (layer.source.params or {}).get('b')]
    if not own and all(project.layer(r).group_id is None for r in refs) and layer.tween_input_transform == Affine() and not layer.tween_reference_transforms:
        return Affine(), {r:project.layer(r).transform for r in refs}
    input_tf = mul(mul(inverse(layer.transform), mul(world(project,layer.group_id),layer.transform)), layer.tween_input_transform)
    result = {}
    for rid in refs:
        ref = project.layer(rid)
        shared = []
        for a,b in zip(own,chain(project,ref.group_id)):
            if a != b: break
            shared.append(a)
        shared_tf = world(project, shared[-1] if shared else None)
        # Nested materialized tweens already carry their group input placement.
        base = ref.transform if ref.source.type == 'tween' else mul(world(project,ref.group_id),ref.transform)
        result[rid] = mul(layer.tween_reference_transforms.get(rid,Affine()),mul(inverse(shared_tf),base))
    return input_tf, result


def placed_project(project):
    """Ephemeral model, no hierarchy or source mutations during resolve."""
    layers = []
    for l in project.layers:
        tf = l.transform if l.source.type == 'tween' else mul(world(project,l.group_id),l.transform)
        placed = l.model_copy(update={'transform':tf,'visible':visible(project,l)})
        if l.source.type == 'tween':
            origin = mul(world(project,l.group_id),mul(l.transform,l.tween_input_transform)).translation
            if origin != l.transform.translation:
                placed._effect_translation = origin
        layers.append(placed)
    return project.model_copy(update={'layers':layers})


def tween_source_correction(project, layer, master_t=None, depth=0):
    """Placement introduced by hierarchy edits relative to legacy parameter morphs.

    Parameter-space nesting regenerates the underlying generator rather than
    interpolating materialized drawings. Carry its extra reference frame through
    that reduction so shared ancestry cancels before affine interpolation.
    """
    if layer.source.type != 'tween' or depth > 8:
        return Affine()
    from .tween import (chain_key_ids, chain_segment, lerp_affine,
                        master_driven_curve, resolve_local_t)
    params = layer.source.params or {}
    keys = chain_key_ids(params)
    u = resolve_local_t(params, master_t)
    if keys:
        seg, t = chain_segment(u, len(keys), master_driven_curve(params, master_t))
        a, b = keys[seg:seg+2]
    else:
        a, b, t = params['a'], params['b'], u
    la, lb = project.layer(a), project.layer(b)
    c, refs = tween_frames(project, layer)
    ra = mul(refs[a], tween_source_correction(project, la, master_t, depth+1))
    rb = mul(refs[b], tween_source_correction(project, lb, master_t, depth+1))
    ba = layer.tween_reference_baselines.get(a, la.transform)
    bb = layer.tween_reference_baselines.get(b, lb.transform)
    if c == Affine() and ra == ba and rb == bb:
        return Affine()
    left_delta, right_delta = mul(ra, inverse(ba)), mul(rb, inverse(bb))
    # A common placement factors out without inverting the interpolated
    # reference matrix. That matrix may collapse at a mirrored midpoint.
    if all(math.isclose(v, right_delta.model_dump()[k], rel_tol=1e-10, abs_tol=1e-10)
           for k, v in left_delta.model_dump().items()):
        return mul(c, left_delta)
    baseline = lerp_affine(ba, bb, t)
    try:
        inv_baseline = inverse(baseline)
    except ValueError:
        # A reflected reference can collapse mid-frame despite valid endpoint
        # placements. Interpolate their additional placement in that case.
        return mul(c, lerp_affine(left_delta, right_delta, t))
    return mul(mul(c, lerp_affine(ra, rb, t)), inv_baseline)
