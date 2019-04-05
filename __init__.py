bl_info = {
    'name': 'Particle Hair Guides',
    'author': 'Alexander Meißner',
    'version': (0,0,1),
    'blender': (2,7,9),
    'location': 'Properties',
    'category': 'Particle',
    'description': 'Generates hair particles from mesh edges which start at marked seams'
}

import bpy, bmesh, math
import mathutils, random
from mathutils import Vector

def bisect_lower_bound(key_index, a, x, low, high):
    while low < high:
        mid = (low+high)//2
        if a[mid][key_index] < x: low = mid+1
        else: high = mid
    return low

class GenerateParticleHair(bpy.types.Operator):
    bl_idname = 'particle.generate_particle_hair'
    bl_label = 'Particle Hair from Mesh'
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = 'Generates hair particles from mesh edges which start at marked seams'

    connect = bpy.props.BoolProperty(name='Connect', description='Connect roots to the emitters surface', default=False)
    spacing = bpy.props.FloatProperty(name='Spacing', unit='LENGTH', description='Average distance between two hairs', min=0.00001, default=1.0)
    tangent_random = bpy.props.FloatVectorProperty(name='Tangent Random', unit='LENGTH', description='Randomness inside a strand (at root, uniform, towards tip)', min=0.0, default=(0.0, 0.0, 0.0), size=3)
    normal_random = bpy.props.FloatVectorProperty(name='Normal Random', unit='LENGTH', description='Randomness towards surface normal (at root, uniform, towards tip)', min=0.0, default=(0.0, 0.0, 0.0), size=3)
    length_random = bpy.props.FloatProperty(name='Length Random', description='Variation of hair length', min=0.0, max=1.0, default=0.0)
    random_seed = bpy.props.IntProperty(name='Random Seed', description='Increase to get a different result', min=0, default=0)

    @classmethod
    def poll(self, context):
        return (context.mode == 'OBJECT' and context.object.particle_systems.active and context.object.particle_systems.active.settings.type == 'HAIR')

    def execute(self, context):
        dst_obj = context.object
        inverse_transform = dst_obj.matrix_world.inverted()
        strands = []
        stats = {
            'hair_count': 0,
            'strand_steps': None
        }
        dst_obj.select = False
        for src_obj in context.selected_objects:
            if src_obj.type != 'MESH':
                continue
            src_obj.hide = True
            transform = inverse_transform*src_obj.matrix_world
            data = bm = bmesh.new()
            bm.from_object(src_obj, bpy.context.scene, deform=True, render=False, cage=False, face_normals=True)
            for edge in data.edges:
                if edge.seam and len(edge.link_loops) == 1:
                    loop = edge.link_loops[0]
                    side_A = transform*loop.edge.other_vert(loop.vert).co
                    side_B = transform*loop.vert.co
                    position = (side_A+side_B)*0.5
                    step = (0, position, side_B-side_A, transform*loop.vert.normal)
                    steps = [step]
                    while True:
                        loop = loop.link_loop_next.link_loop_next
                        side_A = transform*loop.vert.co
                        side_B = transform*loop.edge.other_vert(loop.vert).co
                        position = (side_A+side_B)*0.5
                        step = (step[0]+(position-step[1]).length, position, side_B-side_A, transform*loop.vert.normal)
                        steps.append(step)
                        if len(loop.link_loops) != 1:
                            break
                        loop = loop.link_loops[0]
                    if stats['strand_steps'] == None:
                        stats['strand_steps'] = len(steps)
                    elif stats['strand_steps'] != len(steps):
                        self.report({'WARNING'}, 'Some strands have a different number of vertices')
                        return {'CANCELLED'}
                    strand_hairs = max(1, round((side_A-side_B).length/self.spacing))
                    stats['hair_count'] += strand_hairs
                    strands.append((strand_hairs, steps))
            bm.free()

        if stats['strand_steps'] == None:
            self.report({'WARNING'}, 'Could not find any marked edges')
            return {'CANCELLED'}
        if stats['strand_steps'] < 3:
            self.report({'WARNING'}, 'Strands must be at least two faces long')
            return {'CANCELLED'}
        if stats['hair_count'] > 10000:
            self.report({'WARNING'}, 'Trying to create more than 10000 hairs, try to decrease the density')
            return {'CANCELLED'}

        dst_obj.select = True
        bpy.context.scene.objects.active = dst_obj
        pasy = dst_obj.particle_systems.active
        pamo = None
        for modifier in dst_obj.modifiers:
            if isinstance(modifier, bpy.types.ParticleSystemModifier) and modifier.particle_system == pasy:
                pamo = modifier
                break
        pamo.show_viewport = True
        bpy.ops.particle.edited_clear()
        pasy.settings.hair_step = stats['strand_steps']-1
        pasy.settings.count = stats['hair_count']
        bpy.ops.particle.particle_edit_toggle()

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
                for step_index in range(0, stats['strand_steps']):
                    length_param = steps[step_index][0]*length_factor
                    remapped_step_index = bisect_lower_bound(0, steps, length_param, 0, stats['strand_steps'])
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

        # Mark particle system as edited
        bpy.context.scene.tool_settings.particle_edit.tool = 'COMB'
        bpy.ops.particle.brush_edit(stroke=[{'name': '', 'location': (0, 0, 0), 'mouse': (0, 0), 'pressure': 0, 'size': 0, 'pen_flip': False, 'time': 0, 'is_start': False}])
        bpy.context.scene.tool_settings.particle_edit.tool = 'NONE'

        bpy.ops.particle.particle_edit_toggle()
        if self.connect:
            bpy.ops.particle.disconnect_hair(all=True)
            bpy.ops.particle.connect_hair(all=True)
        return {'FINISHED'}


def register():
    bpy.utils.register_module(__name__)

def unregister():
    bpy.utils.unregister_module(__name__)

if __name__ == '__main__':
    register()
