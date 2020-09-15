# Particle Hair Guides
An add-on for [Blender 3D](https://www.blender.org/) 2.79, 2.83 and 2.90 to generate randomized particle hair form meshes, curves and nurbs.
Please select the git branch according to your Blender version.

## Usage
- 1. Create some strands as source:
  - Mesh: Hair roots will be at the edges marked as seams
  - Bezier curve: Spline type must be "Bezier" and Handle type must be "Automatic", "Aligned" or "Free" (not "Vector")
    - Ribbons by setting Extrude > 0
    - Bundles by setting Bevel Depth > 0
  - Nurbs surface: Hair roots will be at an orange edge and be parallel to the magenta edges
- 2. Make sure all strands have the same number of vertices from the root to the tip (must be at least 2).
- 3. Select this source mesh and then additionally select the target object (particle emitter) so it becomes active.
- 4. Add to or select an existing a particle system in the emitter object.
- 5. Make sure the particle system settings are set to type "Hair" (not "Emitter").
- 6. In the 3D view go to "Object" > "Hair Guides" > "Particle Hair from Guides" and apply the operator.
- 7. Tweak the operators options.
