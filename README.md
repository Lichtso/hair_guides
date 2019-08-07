# Particle Hair Guides
An addon for [Blender 3D](https://www.blender.org/) 2.79 and 2.80 to generate randomized particle hair form meshes, curves and nurbs.
Please select the git branch according to your Blender version.

## Usage
- 1. Create some strands as source:
  - Mesh: Hair roots will be at the edges marked as seams
  - or bezier curves: Handle type must not be "Vector" and Curve > Geometry > Extrude defines the width of the ribbons (must be greater than zero)
  - or nurbs surfaces: Hair roots will be at an orange edge and be parallel to the magenta edges
- 2. Make sure all strands have the same number of vertices from the root to the tip (must be at least 2).
- 3. Select this source mesh and then additionally select the target object (particle emitter) so it becomes active.
- 4. Add to or select an existing a particle system in the emitter object.
- 5. Make sure the particle system settings are set to type "Hair" (not "Emitter").
- 6. Search "Particle Hair" and apply the operator.
- 7. Tweak the operators options.
