"""Atomic hierarchy editing. Validate detached candidate before one undo checkpoint."""
import uuid
from .compose import Affine, LayerGroup, layer_effect_seed
from .groups import (chain, descendants, group, inverse, mul, normalize, parent,
                     siblings, target_layers, tween_frames, validate_hierarchy, world)


class GroupSessionMixin:
    def _hierarchy_candidate(self):
        import copy
        return copy.deepcopy(self.project,{id(g):g for g in self.project.staging})

    def _commit_hierarchy(self, candidate, geometry=None):
        validate_hierarchy(candidate)
        self._checkpoint()
        self.project = candidate
        if geometry is not None:
            self.source_geometry = geometry

    def create_group(self, targets, name='Group'):
        with self._lock:
            ts = normalize(self.project, targets)
            if not ts:
                raise ValueError('select neighboring items to group')
            pid = parent(self.project, ts[0])
            if any(parent(self.project,t) != pid for t in ts):
                raise ValueError('group only consecutive siblings')
            order = siblings(self.project,pid)
            indices = sorted(order.index(t) for t in ts)
            if indices != list(range(indices[0],indices[-1]+1)):
                raise ValueError('group only consecutive siblings')
            p = self._hierarchy_candidate()
            g = LayerGroup(name=name, parent_id=pid)
            p.groups.append(g)
            for t in ts:
                if t['kind'] == 'group': group(p,t['id']).parent_id = g.id
                else:
                    for l in target_layers(p,t): l.group_id = g.id
            self._commit_hierarchy(p)
            return g

    def update_group(self, gid, patch):
        with self._lock:
            if set(patch) - {'name','visible','transform'}:
                raise ValueError('use reparent for group membership')
            p = self._hierarchy_candidate()
            old = group(p,gid)
            updated = LayerGroup.model_validate({**old.model_dump(),**patch})
            if "visible" in patch: updated.inherited_visible = True
            p.groups[p.groups.index(old)] = updated
            self._commit_hierarchy(p)
            return updated

    def _frames_before(self):
        return {l.id:(*tween_frames(self.project,l),
                      {rid:l.tween_reference_baselines.get(rid,self.project.layer(rid).transform)
                       for rid in self._tween_refs(l)})
                for l in self.project.layers if l.source.type == 'tween'}

    @staticmethod
    def _preserve_frames(p, frames):
        for lid,(old_input,old_refs,baselines) in frames.items():
            l = p.layer(lid)
            l.tween_input_transform = Affine()
            l.tween_reference_transforms = {}
            l.tween_reference_baselines = baselines
            new_input,new_refs = tween_frames(p,l)
            l.tween_input_transform = mul(inverse(new_input),old_input)
            l.tween_reference_transforms = {i:mul(r,inverse(new_refs[i])) for i,r in old_refs.items()}

    def ungroup(self, gid):
        return self.ungroup_selection([{'kind':'group','id':gid}])

    def ungroup_selection(self, targets):
        with self._lock:
            ts = normalize(self.project, targets)
            if not ts or any(t['kind'] != 'group' for t in ts):
                raise ValueError('select groups to ungroup')
            frames = self._frames_before()
            p = self._hierarchy_candidate()
            result = []
            for target in ts:
                g = group(p,target['id'])
                children = siblings(p,g.id)
                result.extend(children)
                for t in children:
                    if t['kind'] == 'group':
                        child = group(p,t['id'])
                        child.transform = mul(g.transform,child.transform)
                        child.inherited_visible = child.inherited_visible and g.visible and g.inherited_visible
                        child.parent_id = g.parent_id
                    else:
                        for l in target_layers(p,t):
                            if l.source.type != 'tween': l.transform = mul(g.transform,l.transform)
                            l.inherited_visible = l.inherited_visible and g.visible and g.inherited_visible
                            l.group_id = g.parent_id
                p.groups.remove(g)
            self._preserve_frames(p,frames)
            self._commit_hierarchy(p)
            return result

    def transform_selection(self, targets, delta):
        with self._lock:
            delta = Affine.model_validate(delta)
            inverse(delta)
            ts = normalize(self.project,targets)
            if not ts: raise ValueError('empty selection')
            p = self._hierarchy_candidate()
            for t in ts:
                if t['kind'] == 'group':
                    g = group(p,t['id']); pw = world(p,g.parent_id)
                    g.transform = mul(mul(mul(inverse(pw),delta),pw),g.transform)
                else:
                    for l in [p.layer(t["id"])]:
                        if l.source.type == 'tween':
                            # Apply placement at the input, before millimetre effects.
                            base = mul(inverse(l.transform),mul(world(p,l.group_id),l.transform))
                            conjugated = mul(inverse(l.transform),mul(delta,l.transform))
                            l.tween_input_transform = mul(inverse(base),mul(conjugated,mul(base,l.tween_input_transform)))
                            inverse(l.tween_input_transform)
                        else:
                            pw = world(p,l.group_id)
                            l.transform = mul(mul(mul(inverse(pw),delta),pw),l.transform)
                            inverse(l.transform)
            self._commit_hierarchy(p)
            return ts

    def reparent_selection(self, targets, parent_id=None, before_id=None):
        with self._lock:
            ts = normalize(self.project,targets)
            if not ts: raise ValueError('empty selection')
            if parent_id:
                group(self.project,parent_id)
                if any(t['kind']=='group' and t['id'] in chain(self.project,parent_id) for t in ts):
                    raise ValueError('group cycle')
            frames = self._frames_before()
            p = self._hierarchy_candidate()
            dest = world(p,parent_id)
            moved_ids = {l.id for t in ts for l in target_layers(p,t)}
            block = [l for l in p.layers if l.id in moved_ids]
            for t in ts:
                if t['kind']=='group':
                    g = group(p,t['id']); old_world = world(p,g.id)
                    g.parent_id = parent_id; g.transform = mul(inverse(dest),old_world)
                else:
                    for l in target_layers(p,t):
                        old_world = mul(world(p,l.group_id),l.transform)
                        if l.source.type != 'tween': l.transform = mul(inverse(dest),old_world)
                        l.group_id = parent_id
            remaining = [l for l in p.layers if l.id not in moved_ids]
            if before_id:
                target = next((t for t in siblings(p,parent_id) if t['id']==before_id),None)
                if not target or before_id in {t['id'] for t in ts}: raise ValueError('invalid reorder destination')
                first = target_layers(p,target)[0].id
                idx = next(i for i,l in enumerate(remaining) if l.id==first)
            elif parent_id:
                ids = {l.id for l in descendants(p,parent_id)} - moved_ids
                idx = max((i+1 for i,l in enumerate(remaining) if l.id in ids),default=len(remaining))
            else: idx = len(remaining)
            p.layers = remaining[:idx]+block+remaining[idx:]
            # Moving the final child removes empty ancestors.
            p.groups = [g for g in p.groups if descendants(p,g.id)]
            self._preserve_frames(p,frames)
            self._commit_hierarchy(p)
            return ts

    def duplicate_selection(self, targets):
        with self._lock:
            ts = normalize(self.project,targets)
            if not ts: raise ValueError('empty selection')
            p = self._hierarchy_candidate()
            ids = {l.id for t in ts for l in target_layers(p,t)}
            gids = {g.id for g in p.groups if any(t['kind']=='group' and t['id'] in chain(p,g.id) for t in ts)}
            remap = {i:uuid.uuid4().hex[:8] for i in ids|gids}
            newgroups = []
            for g in p.groups:
                if g.id in gids:
                    copy = g.model_copy(deep=True); copy.id = remap[g.id]
                    copy.parent_id = remap.get(g.parent_id,g.parent_id); copy.name += ' copy'
                    newgroups.append(copy)
            p.groups.extend(newgroups)
            geo = dict(self.source_geometry)
            copies = {}
            for l in p.layers:
                if l.id not in ids: continue
                copy = l.model_copy(deep=True); copy.id = remap[l.id]; copy.name += ' copy'
                copy.effect_seed = layer_effect_seed(l)
                copy.group_id = remap.get(l.group_id,l.group_id)
                copy.animation_owner_id = remap.get(l.animation_owner_id,l.animation_owner_id)
                if copy.source.type == 'tween':
                    params = copy.source.params or {}
                    for k in ('a','b'): params[k] = remap.get(params.get(k),params.get(k))
                    if params.get('keys'): params['keys'] = [remap.get(k,k) for k in params['keys']]
                    copy.tween_reference_transforms = {remap.get(k,k):v for k,v in copy.tween_reference_transforms.items()}
                    copy.tween_reference_baselines = {remap.get(k,k):v for k,v in copy.tween_reference_baselines.items()}
                geo[copy.id] = self.source_geometry.get(l.id,[])
                copies[l.id] = copy
            # Each selected block is duplicated adjacent to itself, preserving sibling order.
            for t in reversed(sorted(ts,key=lambda t:p.layers.index(target_layers(p,t)[0]))):
                members = target_layers(p,t)
                idx = max(p.layers.index(l) for l in members)+1
                p.layers[idx:idx] = [copies[l.id] for l in members]
            self._commit_hierarchy(p,geo)
            return [{'kind':t['kind'],'id':remap[t['id']]} for t in ts]

    def delete_selection(self, targets):
        with self._lock:
            ts = normalize(self.project,targets)
            if not ts: raise ValueError('empty selection')
            ids = {l.id for t in ts for l in target_layers(self.project,t)}
            # Existing family/reference dependency deletion creates one checkpoint.
            removed = self.delete_layers(list(ids))
            self.project.groups = [g for g in self.project.groups if descendants(self.project,g.id)]
            return removed
