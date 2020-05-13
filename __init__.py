bl_info = {
    'name': 'Particle Hair from Guides',
    'author': 'Alexander Meißner',
    'version': (0,0,1),
    'blender': (2,80,0),
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
        if isinstance(modifier, bpy.types.ParticleSystemModifier) and modifier.particle_system == pasy:
            pamo = modifier
            break
    return (pasy, pamo)

def beginParticleHairUpdate(context, obj):
    bpy.ops.particle.particle_edit_toggle()
    bpy.context.scene.tool_settings.particle_edit.tool = 'COMB'
    bpy.ops.particle.brush_edit(stroke=[{'name': '', 'location': (0, 0, 0), 'mouse': (0, 0), 'pressure': 0, 'size': 0, 'pen_flip': False, 'time': 0, 'is_start': False}])
    bpy.ops.particle.particle_edit_toggle()
    depsgraph = context.evaluated_depsgraph_get()
    obj = obj.evaluated_get(depsgraph)
    pasy = obj.particle_systems.active
    return (obj, pasy)

def finishParticleHairUpdate():
    bpy.ops.particle.particle_edit_toggle()
    bpy.ops.particle.particle_edit_toggle()

class ParticleHairFromGuides(bpy.types.Operator):
    bl_idname = 'particle.hair_from_guides'
    bl_label = 'Particle Hair from Guides'
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = 'Generates hair particles from meshes (seam edges), bezier curves or nurbs surfaces.'

    spacing: bpy.props.FloatProperty(name='Spacing', unit='LENGTH', description='Average distance between two hairs', min=0.00001, default=1.0)
    tangent_random: bpy.props.FloatVectorProperty(name='Tangent Random', description='Randomness inside a strand (at root, uniform, towards tip)', min=0.0, default=(0.0, 0.0, 0.0), size=3)
    normal_random: bpy.props.FloatVectorProperty(name='Normal Random', description='Randomness towards surface normal (at root, uniform, towards tip)', min=0.0, default=(0.0, 0.0, 0.0), size=3)
    length_random: bpy.props.FloatProperty(name='Length Random', description='Variation of hair length', min=0.0, max=1.0, default=0.0)
    random_seed: bpy.props.IntProperty(name='Random Seed', description='Increase to get a different result', min=0, default=0)

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
                        if spline.resolution_u < 2:
                            self.report({'WARNING'}, 'Curve resolution U must be at least 2')
                            return {'CANCELLED'}
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
            mesh.from_object(src_obj, depsgraph, deform=True, cage=False, face_normals=True)
            mesh.transform(inverse_transform@src_obj.matrix_world)
            for edge in mesh.edges:
                if edge.seam and len(edge.link_loops) == 1:
                    loop = edge.link_loops[0]
                    side_A = loop.edge.other_vert(loop.vert).co
                    side_B = loop.vert.co
                    position = (side_A+side_B)*0.5
                    step = (0, position, side_B-side_A, Vector(loop.vert.normal))
                    steps = [step]
                    strand_hairs = max(1, round((side_A-side_B).length/self.spacing))
                    hair_count += strand_hairs
                    strands.append((strand_hairs, steps))
                    while True:
                        loop = loop.link_loop_next.link_loop_next
                        side_A = loop.vert.co
                        side_B = loop.edge.other_vert(loop.vert).co
                        position = (side_A+side_B)*0.5
                        step = (step[0]+(position-step[1]).length, position, side_B-side_A, Vector(loop.vert.normal))
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
        pasy, pamo = getParticleSystem(dst_obj)
        pamo.show_viewport = True
        bpy.ops.particle.edited_clear()
        pasy.settings.hair_step = hair_steps-1
        pasy.settings.count = hair_count
        dst_obj, pasy = beginParticleHairUpdate(context, dst_obj)

        hair_index = 0
        randomgen = random.Random()
        randomgen.seed(self.random_seed)
        for strand in strands:
            strand_hairs = strand[0]
            steps = strand[1]
            for index_in_strand in range(0, strand_hairs):
                tangent_random_at_root = (randomgen.random()-0.5)*self.tangent_random[0]
                tangent_random_towards_tip = (randomgen.random()-0.5)*self.tangent_random[2]
                normal_random_at_root = (randomgen.random()-0.5)*self.normal_random[0]
                normal_random_towards_tip = (randomgen.random()-0.5)*self.normal_random[2]
                length_factor = 1.0-randomgen.random()*self.length_random
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
                    vertex = pasy.particles[hair_index].hair_keys[step_index]
                    vertex.co = position+tangent*((index_in_strand+0.5)/strand_hairs-0.5)
                    vertex.co += tangent.normalized()*(tangent_random_at_root+(randomgen.random()-0.5)*self.tangent_random[1]+tangent_random_towards_tip*length_param)
                    vertex.co += normal.normalized()*(normal_random_at_root+(randomgen.random()-0.5)*self.normal_random[1]+normal_random_towards_tip*length_param)
                pasy.particles[hair_index].location = pasy.particles[hair_index].hair_keys[0].co
                hair_index += 1

        finishParticleHairUpdate()
        return {'FINISHED'}

class SaveParticleHairToMesh(bpy.types.Operator):
    bl_idname = 'particle.save_hair_to_mesh'
    bl_label = 'Save Particle Hair to Mesh'
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = 'Creates a mesh from active particle hair system'

    def execute(self, context):
        if not validateContext(self, context):
            return {'CANCELLED'}
        depsgraph = bpy.context.evaluated_depsgraph_get()
        src_obj = context.object.evaluated_get(depsgraph)
        pasy, pamo = getParticleSystem(src_obj)
        steps = pasy.settings.hair_step+1

        dst_name = pasy.name
        mesh_data = bpy.data.meshes.new(name=dst_name)
        dst_obj = bpy.data.objects.new(dst_name, mesh_data)
        dst_obj.matrix_world = src_obj.matrix_world
        bpy.context.scene.collection.objects.link(dst_obj)
        bpy.ops.object.select_all(action='DESELECT')
        dst_obj.select_set(True)
        bpy.context.view_layer.objects.active = dst_obj

        vertices = []
        edges = []
        faces = []
        for hair_index in range(0, pasy.settings.count):
            hair = pasy.particles[hair_index]
            for step_index in range(0, steps):
                if step_index > 0:
                    edges.append((len(vertices)-1, len(vertices)))
                vertices.append(hair.hair_keys[step_index].co)
        mesh_data.from_pydata(vertices, edges, faces)
        mesh_data.update()

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='VERT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        for hair_index in range(0, pasy.settings.count):
            mesh_data.vertices[hair_index*steps].select = True

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

        hair_steps = None
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
                if hair_steps == None:
                    hair_steps = len(loop)
                elif hair_steps != len(loop):
                    self.report({'WARNING'}, 'Some hairs have a different number of vertices')
                    return {'CANCELLED'}

        pasy, pamo = getParticleSystem(dst_obj)
        pasy.settings.use_modifier_stack = False # Work around for: https://developer.blender.org/T54488
        pamo.show_viewport = True
        bpy.ops.particle.edited_clear()
        pasy.settings.hair_step = hair_steps-1
        pasy.settings.count = hair_count
        dst_obj, pasy = beginParticleHairUpdate(context, dst_obj)

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
                hair_index += 1
                for step_index in range(0, hair_steps):
                    hair.hair_keys[step_index].co = transform@src_obj.data.vertices[loop[step_index]].co

        finishParticleHairUpdate()
        bpy.ops.particle.disconnect_hair()
        bpy.ops.particle.connect_hair()
        return {'FINISHED'}

register, unregister = bpy.utils.register_classes_factory([ParticleHairFromGuides, SaveParticleHairToMesh, RestoreParticleHairFromMesh])
