bl_info = {
    'name': 'Particle Hair from Guides',
    'author': 'Alexander Meißner',
    'version': (0,0,1),
    'blender': (3,0,0),
    'category': 'Particle',
    'wiki_url': 'https://github.com/lichtso/hair_guides/',
    'tracker_url': 'https://github.com/lichtso/hair_guides/issues',
    'description': 'Generates hair particles from meshes (seam edges), bezier curves or nurbs surfaces.'
}

import bpy, bmesh, math
import mathutils, random
from bpy_extras import mesh_utils
from mathutils import Vector

def bisectLowerBound(key_index, a, x, low, high):
    while low < high:
        mid = (low+high)//2
        if a[mid][key_index] < x: low = mid+1
        else: high = mid
    return low

def copyAttributes(dst, src):
    for attribute in dir(src):
        try:
            setattr(dst, attribute, getattr(src, attribute))
        except:
            pass

def validateContext(self, context):
    if context.mode != 'OBJECT':
        self.report({'WARNING'}, 'Not in object mode')
        return False
    if not context.object:
        self.report({'WARNING'}, 'No target selected as active')
        return False
    if not context.object.particle_systems.active:
        self.report({'WARNING'}, 'Target has no active particle system')
        return False
    if context.object.particle_systems.active.settings.type != 'HAIR':
        self.report({'WARNING'}, 'The targets active particle system is not of type "hair"')
        return False
    return True

def getParticleSystem(obj):
    pasy = obj.particle_systems.active
    pamo = None
    for modifier in obj.modifiers:
        if modifier.type == "PARTICLE_SYSTEM" and modifier.particle_system == pasy:
            pamo = modifier
            break
    return (pasy, pamo)

def beginParticleHairUpdate(context, dst_obj, hair_steps, hair_count):
    pasy, pamo = getParticleSystem(dst_obj)
    pamo.show_viewport = True
    bpy.ops.particle.edited_clear()
    pasy.settings.hair_step = hair_steps-1
    pasy.settings.count = hair_count
    bpy.ops.object.mode_set(mode='PARTICLE_EDIT')
    bpy.ops.object.mode_set(mode='OBJECT')
    pamo = dst_obj.modifiers[pamo.name]
    pasy = pamo.particle_system
    depsgraph = context.evaluated_depsgraph_get()
    dst_obj_eval = dst_obj.evaluated_get(depsgraph)
    pamo_eval = dst_obj_eval.modifiers[pamo.name]
    pasy_eval = pamo_eval.particle_system
    return (pasy, dst_obj_eval, pamo_eval, pasy_eval)

class ParticleHairFromGuides(bpy.types.Operator):
    bl_idname = 'particle.hair_from_guides'
    bl_label = 'Particle Hair from Guides'
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = 'Generates hair particles from meshes (seam edges), bezier curves or nurbs surfaces.'

    spacing: bpy.props.FloatProperty(name='Spacing', unit='LENGTH', description='Average distance between two hairs. Decease this to increase density.', min=0.00001, default=1.0)
    length_rand: bpy.props.FloatProperty(name='Length Rand', description='Randomness of hair length', min=0.0, max=1.0, default=0.0)
    rand_at_root: bpy.props.FloatVectorProperty(name='Rand at Root', description='Randomness at the roots (tangent, normal)', default=(0.0, 0.0), size=2)
    uniform_rand: bpy.props.FloatVectorProperty(name='Uniform Rand', description='Randomness inside the entire strand (tangent, normal)', default=(0.0, 0.0), size=2)
    rand_towards_tip: bpy.props.FloatVectorProperty(name='Rand towards Tip', description='Randomness increasing towards the tip (tangent, normal)', default=(0.0, 0.0), size=2)
    uniform_bias: bpy.props.FloatVectorProperty(name='Uniform Bias', description='Bias at the roots (tangent, normal)', default=(0.0, 0.0), size=2)
    bias_towards_tip: bpy.props.FloatVectorProperty(name='Bias towards Tip', description='Bias increasing towards the tip (tangent, normal)', default=(0.0, 0.0), size=2)
    couple_root_and_tip: bpy.props.BoolProperty(name='Couple Root & Tip', description='Couples the randomness at the root and the tip', default=False)
    rand_seed: bpy.props.IntProperty(name='Rand Seed', description='Increase to get a different result', default=0)

    def execute(self, context):
        if not validateContext(self, context):
            return {'CANCELLED'}
        depsgraph = context.evaluated_depsgraph_get()
        dst_obj = context.object
        inverse_transform = dst_obj.matrix_world.inverted()
        tmp_objs = []
        strands = []
        hair_count = 0
        hair_steps = None
        dst_obj.select_set(False)
        if len(context.selected_objects) == 0:
            self.report({'WARNING'}, 'No source objects selected')
            return {'CANCELLED'}
        for src_obj in context.selected_objects:
            if src_obj.type == 'CURVE' or src_obj.type == 'SURFACE':
                indices = []
                vertex_index = 0
                if src_obj.type == 'CURVE':
                    if src_obj.data.bevel_depth == 0.0 and src_obj.data.extrude == 0.0:
                        self.report({'WARNING'}, 'Curve must have extrude or bevel depth')
                        return {'CANCELLED'}
                    resolution_u = 2 if src_obj.data.bevel_depth == 0.0 else (4 if src_obj.data.extrude == 0.0 else 3)+2*src_obj.data.bevel_resolution
                    for spline in src_obj.data.splines:
                        if spline.type != 'BEZIER':
                            self.report({'WARNING'}, 'Curve spline type must be Bezier')
                            return {'CANCELLED'}
                        for bezier_point in spline.bezier_points:
                            if bezier_point.handle_left_type == 'VECTOR' or bezier_point.handle_right_type == 'VECTOR':
                                self.report({'WARNING'}, 'Curve handle type must not be Vector')
                                return {'CANCELLED'}
                        resolution_v = (spline.resolution_u*(spline.point_count_u-1)+1)
                        indices.append((vertex_index, resolution_u-1, 1))
                        vertex_index += resolution_u*resolution_v
                        if src_obj.data.bevel_depth != 0.0 and src_obj.data.extrude != 0.0:
                            indices.append((vertex_index, 1, 1))
                            vertex_index += 2*resolution_v
                            indices.append((vertex_index, 1, 1))
                            vertex_index += 2*resolution_v
                            indices.append((vertex_index, resolution_u-1, 1))
                            vertex_index += resolution_u*resolution_v
                elif src_obj.type == 'SURFACE':
                    for spline in src_obj.data.splines:
                        resolution_u = spline.resolution_u*spline.point_count_u
                        resolution_v = spline.resolution_v*spline.point_count_v
                        indices.append((vertex_index, resolution_u-1, resolution_v))
                        vertex_index += resolution_u*resolution_v
                bpy.ops.object.select_all(action='DESELECT')
                src_modifiers = []
                for src_modifier in src_obj.modifiers.values():
                    if src_modifier.show_viewport:
                        src_modifiers.append(src_modifier)
                        src_modifier.show_viewport = False
                src_obj.select_set(True)
                bpy.context.view_layer.objects.active = src_obj
                bpy.ops.object.convert(target='MESH', keep_original=True)
                src_obj.hide_viewport = True
                src_obj = context.object
                tmp_objs.append(src_obj)
                for src_modifier in src_modifiers:
                    src_modifier.show_viewport = True
                    dst_modifier = src_obj.modifiers.new(name=src_modifier.name, type=src_modifier.type)
                    copyAttributes(dst_modifier, src_modifier)
                for iterator in indices:
                    for vertex_index in range(iterator[0], iterator[0]+iterator[1]*iterator[2]+1, iterator[2]):
                        src_obj.data.vertices[vertex_index].select = True
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_mode(type='VERT')
                bpy.ops.mesh.mark_seam(clear=False)
                bpy.ops.mesh.select_all(action='DESELECT')
                bpy.ops.object.mode_set(mode='OBJECT')
            elif src_obj.type == 'MESH':
                src_obj.hide_viewport = True
            else:
                continue
            mesh = bmesh.new()
            mesh.from_object(src_obj, depsgraph, cage=False, face_normals=True)
            mesh.transform(inverse_transform@src_obj.matrix_world)
            for edge in mesh.edges:
                if edge.seam and len(edge.link_loops) == 1:
                    loop = edge.link_loops[0]
                    side_A = loop.edge.other_vert(loop.vert).co
                    side_B = loop.vert.co
                    position = (side_A+side_B)*0.5
                    step = (0, position, side_B-side_A, Vector(loop.face.normal))
                    steps = [step]
                    strand_hairs = max(1, round((side_A-side_B).length/self.spacing))
                    hair_count += strand_hairs
                    strands.append((strand_hairs, steps))
                    while True:
                        loop = loop.link_loop_next.link_loop_next
                        side_A = loop.vert.co
                        side_B = loop.edge.other_vert(loop.vert).co
                        position = (side_A+side_B)*0.5
                        step = (step[0]+(position-step[1]).length, position, side_B-side_A, Vector(loop.face.normal))
                        steps.append(step)
                        if len(loop.link_loops) != 1:
                            break
                        loop = loop.link_loops[0]
                    if hair_steps == None:
                        hair_steps = len(steps)
                    elif hair_steps != len(steps):
                        self.report({'WARNING'}, 'Some strands have a different number of vertices')
                        return {'CANCELLED'}
            mesh.free()

        if len(tmp_objs) > 0:
            for obj in tmp_objs:
                bpy.data.meshes.remove(obj.data)

        if hair_steps == None:
            self.report({'WARNING'}, 'Could not find any marked edges')
            return {'CANCELLED'}
        if hair_steps < 3:
            self.report({'WARNING'}, 'Strands must be at least two faces long')
            return {'CANCELLED'}
        if hair_count > 10000:
            self.report({'WARNING'}, 'Trying to create more than 10000 hairs, try to decrease the density')
            return {'CANCELLED'}

        dst_obj.select_set(True)
        bpy.context.view_layer.objects.active = dst_obj
        pasy, dst_obj_eval, pamo_eval, pasy_eval = beginParticleHairUpdate(context, dst_obj, hair_steps, hair_count)

        hair_index = 0
        randomgen = random.Random()
        randomgen.seed(self.rand_seed)
        for strand in strands:
            strand_hairs = strand[0]
            steps = strand[1]
            for index_in_strand in range(0, strand_hairs):
                tangent_rand = randomgen.random()-0.5
                normal_rand = randomgen.random()-0.5
                tangent_offset_at_root = self.uniform_bias[0]+tangent_rand*self.rand_at_root[0]
                normal_offset_at_root = self.uniform_bias[1]+normal_rand*self.rand_at_root[1]
                if not self.couple_root_and_tip:
                    tangent_rand = randomgen.random()-0.5
                    normal_rand = randomgen.random()-0.5
                tangent_rand_towards_tip = self.bias_towards_tip[0]+tangent_rand*self.rand_towards_tip[0]
                normal_rand_towards_tip = self.bias_towards_tip[1]+normal_rand*self.rand_towards_tip[1]
                length_factor = 1.0-randomgen.random()*self.length_rand
                hair = pasy.particles[hair_index]
                hair_eval = pasy_eval.particles[hair_index]
                hair_index += 1
                for step_index in range(0, hair_steps):
                    length_param = steps[step_index][0]*length_factor
                    remapped_step_index = bisectLowerBound(0, steps, length_param, 0, hair_steps)
                    step = steps[remapped_step_index]
                    if step_index == 0:
                        position = step[1]
                        tangent = step[2]
                        normal = step[3]
                    else:
                        prev_step = steps[remapped_step_index-1]
                        coaxial_param = (length_param-prev_step[0])/(step[0]-prev_step[0])
                        position = prev_step[1]+(step[1]-prev_step[1])*coaxial_param
                        tangent = prev_step[2]+(step[2]-prev_step[2])*coaxial_param
                        normal = prev_step[3]+(step[3]-prev_step[3])*coaxial_param
                    co = position+tangent*((index_in_strand+0.5)/strand_hairs-0.5)
                    co += tangent.normalized()*(tangent_offset_at_root+(randomgen.random()-0.5)*self.uniform_rand[0]+tangent_rand_towards_tip*length_param)
                    co += normal.normalized()*(normal_offset_at_root+(randomgen.random()-0.5)*self.uniform_rand[1]+normal_rand_towards_tip*length_param)
                    hair.hair_keys[step_index].co_object_set(dst_obj_eval, pamo_eval, hair_eval, co)
                    if step_index == 0:
                        hair.location = co

        bpy.ops.particle.disconnect_hair()
        return {'FINISHED'}

class SaveParticleHairToMesh(bpy.types.Operator):
    bl_idname = 'particle.save_hair_to_mesh'
    bl_label = 'Save Particle Hair to Mesh'
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = 'Creates a mesh from active particle hair system'

    def execute(self, context):
        if not validateContext(self, context):
            return {'CANCELLED'}
        src_obj = context.object
        depsgraph = context.evaluated_depsgraph_get()
        pasy, pamo = getParticleSystem(src_obj)
        src_obj_eval = src_obj.evaluated_get(depsgraph)
        pamo_eval = src_obj_eval.modifiers[pamo.name]
        pasy_eval = pamo_eval.particle_system

        dst_name = pasy.name
        mesh_data = bpy.data.meshes.new(name=dst_name)
        dst_obj = bpy.data.objects.new(dst_name, mesh_data)
        dst_obj.matrix_world = src_obj.matrix_world
        bpy.context.scene.collection.objects.link(dst_obj)

        vertices = []
        edges = []
        hair_steps = []
        for hair_index in range(0, len(pasy.particles)):
            hair = pasy.particles[hair_index]
            hair_eval = pasy_eval.particles[hair_index]
            hair_steps.append(len(hair.hair_keys))
            for step_index in range(0, len(hair.hair_keys)):
                if step_index > 0:
                    edges.append((len(vertices)-1, len(vertices)))
                vertices.append(hair.hair_keys[step_index].co_object(src_obj_eval, pamo_eval, hair_eval))
        mesh_data.from_pydata(vertices, edges, [])
        mesh_data.update()

        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        dst_obj.select_set(True)
        bpy.context.view_layer.objects.active = dst_obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='VERT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        root_index = 0
        for steps in hair_steps:
            mesh_data.vertices[root_index].select = True
            root_index += steps

        return {'FINISHED'}

class RestoreParticleHairFromMesh(bpy.types.Operator):
    bl_idname = 'particle.restore_hair_from_mesh'
    bl_label = 'Restore Particle Hair from Mesh'
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = 'Copies vertices of a mesh to active particle hair system'

    def execute(self, context):
        if not validateContext(self, context):
            return {'CANCELLED'}

        dst_obj = context.object
        dst_obj.select_set(False)
        if len(context.selected_objects) == 0:
            self.report({'WARNING'}, 'No source objects selected')
            return {'CANCELLED'}

        max_hair_steps = 0
        hair_count = 0
        for src_obj in context.selected_objects:
            if src_obj.type != 'MESH':
                continue
            loops = mesh_utils.edge_loops_from_edges(src_obj.data)
            hair_count += len(loops)
            for loop in loops:
                begin_is_selected = src_obj.data.vertices[loop[0]].select
                end_is_selected = src_obj.data.vertices[loop[-1]].select
                if begin_is_selected == end_is_selected:
                    self.report({'WARNING'}, 'The hair roots must be selected and the tips deselected')
                    return {'CANCELLED'}
                max_hair_steps = max(max_hair_steps, len(loop))

        pasy, dst_obj_eval, pamo_eval, pasy_eval = beginParticleHairUpdate(context, dst_obj, max_hair_steps, hair_count)

        hair_index = 0
        inverse_transform = dst_obj.matrix_world.inverted()
        for src_obj in context.selected_objects:
            if src_obj.type != 'MESH':
                continue
            loops = mesh_utils.edge_loops_from_edges(src_obj.data)
            transform = inverse_transform@src_obj.matrix_world
            for loop in loops:
                if not src_obj.data.vertices[loop[0]].select:
                    loop = list(reversed(loop))
                hair = pasy.particles[hair_index]
                hair_eval = pasy_eval.particles[hair_index]
                hair_index += 1
                for step_index in range(0, len(loop)):
                    co = transform@src_obj.data.vertices[loop[step_index]].co
                    hair.hair_keys[step_index].co_object_set(dst_obj_eval, pamo_eval, hair_eval, co)
                    if step_index == 0:
                        hair.location = co
                # for step_index in range(len(loop), max_hair_steps):
                    # hair.hair_keys[step_index].select_set(True)

        # bpy.ops.object.mode_set(mode='PARTICLE_EDIT')
        # bpy.ops.particle.delete(type='KEY')
        # bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.particle.disconnect_hair()
        return {'FINISHED'}

operators = [ParticleHairFromGuides, SaveParticleHairToMesh, RestoreParticleHairFromMesh]

class VIEW3D_MT_object_hair_guides(bpy.types.Menu):
    bl_label = 'Hair Guides'

    def draw(self, context):
        for operator in operators:
            self.layout.operator(operator.bl_idname)

classes = operators+[VIEW3D_MT_object_hair_guides]

def menu_object_hair_guides(self, context):
    self.layout.separator()
    self.layout.menu('VIEW3D_MT_object_hair_guides')

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_object.append(menu_object_hair_guides)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    bpy.types.VIEW3D_MT_object.remove(menu_object_hair_guides)
