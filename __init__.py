bl_info = {
    'name': 'Particle Hair Guides',
    'author': 'Alexander Meißner',
    'version': (0,0,1),
    'blender': (2,7,9),
    'location': 'Properties',
    'category': 'Particle',
    'description': 'Generates hair particles from mesh edges which start at marked seams'
}

import bpy, bmesh
import mathutils, random
from mathutils import Vector

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
        strands = []
        stats = {
            'hair_count': 0,
            'strand_steps': None
        }

        def srcMesh(src_obj, transform):
            src_obj.hide = True
            data = bm = bmesh.new()
            bm.from_object(src_obj, bpy.context.scene, deform=True, render=False, cage=False, face_normals=True)
            for edge in data.edges:
                if edge.seam and len(edge.link_loops) == 1:
                    loop = edge.link_loops[0]
                    begin = transform*loop.edge.other_vert(loop.vert).co
                    end = transform*loop.vert.co
                    tangent = end-begin
                    positions = [(begin, tangent, tangent.normalized(), transform*loop.face.normal)]
                    strand_hairs = round((begin-end).length/self.spacing)
                    while True:
                        loop = loop.link_loop_next.link_loop_next
                        begin = transform*loop.vert.co
                        end = transform*loop.edge.other_vert(loop.vert).co
                        tangent = end-begin
                        positions.append((begin, tangent, tangent.normalized(), transform*loop.face.normal))
                        if len(loop.link_loops) != 1:
                            break
                        loop = loop.link_loops[0]
                    if stats['strand_steps'] == None:
                        stats['strand_steps'] = len(positions)
                    elif stats['strand_steps'] != len(positions):
                        self.report({'WARNING'}, 'Some strands have a different number of vertices')
                        return {'CANCELLED'}
                    stats['hair_count'] += strand_hairs
                    strands.append((strand_hairs, positions))
            bm.free()

        dst_obj = context.object
        for obj in context.selected_objects:
            if not (obj.as_pointer() == dst_obj.as_pointer()):
                if obj.type == 'MESH':
                    srcMesh(obj, dst_obj.matrix_world.inverted()*obj.matrix_world)

        if stats['strand_steps'] == None:
            self.report({'WARNING'}, 'Could not find any marked edges')
            return {'CANCELLED'}
        if stats['strand_steps'] < 3:
            self.report({'WARNING'}, 'Strands must be at least two faces long')
            return {'CANCELLED'}
        if stats['hair_count'] == 0:
            self.report({'WARNING'}, 'No hair was generated, try to increase the density')
            return {'CANCELLED'}
        if stats['hair_count'] > 10000:
            self.report({'WARNING'}, 'Trying to create more than 10000 hairs, try to decrease the density')
            return {'CANCELLED'}

        pasy = dst_obj.particle_systems.active
        pamo = None
        for modifier in dst_obj.modifiers:
            if isinstance(modifier, bpy.types.ParticleSystemModifier) and modifier.particle_system == pasy:
                pamo = modifier
                break
        pamo.show_viewport = True
        pasy.settings.count = stats['hair_count']
        pasy.settings.hair_step = stats['strand_steps']-1
        bpy.ops.particle.particle_edit_toggle()

        index = 0
        randomgen = random.Random()
        randomgen.seed(self.random_seed)
        for strand in strands:
            strand_hairs = strand[0]
            positions = strand[1]
            for index_in_strand in range(0, strand_hairs):
                tangent_random_at_root = (randomgen.random()-0.5)*self.tangent_random[0]
                tangent_random_towards_tip = (randomgen.random()-0.5)*self.tangent_random[2]
                normal_random_at_root = (randomgen.random()-0.5)*self.normal_random[0]
                normal_random_towards_tip = (randomgen.random()-0.5)*self.normal_random[2]
                length_factor = randomgen.random()*self.length_random
                for step in range(0, stats['strand_steps']):
                    vertex = pasy.particles[index].hair_keys[step]
                    vertex.co = positions[step][0]
                    vertex.co += positions[step][1]*index_in_strand/strand_hairs
                    vertex.co += positions[step][2]*(tangent_random_at_root+(randomgen.random()-0.5)*self.tangent_random[1]+tangent_random_towards_tip*step/stats['strand_steps'])
                    vertex.co += positions[step][3]*(normal_random_at_root+(randomgen.random()-0.5)*self.normal_random[1]+normal_random_towards_tip*step/stats['strand_steps'])
                    coaxial = positions[step][0]-positions[step-1][0] if step > 0 else Vector()
                    vertex.co -= coaxial*length_factor
                pasy.particles[index].location = pasy.particles[index].hair_keys[0].co
                index += 1

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
