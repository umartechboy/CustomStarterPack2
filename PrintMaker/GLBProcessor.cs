using System.Numerics;
using System.Reflection;
using System.Security.Cryptography.X509Certificates;
using System.Text.Json.Serialization;
using OpenCvSharp;
using SharpGLTF.Schema2;
using SixLabors.ImageSharp;
using SixLabors.ImageSharp.PixelFormats;
using Image = SixLabors.ImageSharp.Image;


public static class GLBProcessor
{
    public static List<Triangle> Parse(string glbPath)
    {
        var model = ModelRoot.Load(glbPath);
        var rows = new List<Triangle>();
        int meshCounter = 0;
        // Scene traversal with world matrices
        foreach (var scene in model.LogicalScenes)
        {
            foreach (var node in scene.VisualChildren)
                Traverse(node, Matrix4x4.Identity);
        }

        // Dispose images after use

        void Traverse(Node n, Matrix4x4 parentWorld)
        {
            var world = parentWorld * n.LocalMatrix;

            if (n.Mesh != null)
            {
                foreach (var prim in n.Mesh.Primitives)
                {
                    // Vertex/Index data (typed)
                    var pos = prim.GetVertexAccessor("POSITION").AsVector3Array();
                    var mat = prim.Material;

                    // FIX 1: Try multiple color channels
                    var colorChannel = mat.FindChannel("BaseColor") ?? mat.FindChannel("Diffuse");
                    int uvSet = colorChannel?.TextureCoordinate ?? 0;

                    // FIX 2: Check if UVs actually exist before using them
                    var uvs = prim.GetVertexAccessor($"TEXCOORD_{uvSet}")?.AsVector2Array();
                    var cols = prim.GetVertexAccessor("COLOR_0")?.AsVector4Array();
                    var indices = prim.GetIndices().ToArray();

                    // Material color factor - handle both channel types
                    var baseFactor = new float[] { 1, 1, 1, 1 }; // RGBA default
                    if (colorChannel?.Parameters != null)
                    {
                        // Extract color factor from parameters
                        var param = colorChannel?.Parameters.ToList();
                        if (param.Count >= 1)
                        {
                            // Get the actual value from the parameter
                            var value = param[0].Value;
                            if (value is Vector4 colorVec)
                            {
                                baseFactor[0] = colorVec.X;
                                baseFactor[1] = colorVec.Y;
                                baseFactor[2] = colorVec.Z;
                                baseFactor[3] = colorVec.W;
                            }
                            else if (value is Vector3 colorVec3)
                            {
                                baseFactor[0] = colorVec3.X;
                                baseFactor[1] = colorVec3.Y;
                                baseFactor[2] = colorVec3.Z;
                                baseFactor[3] = 1.0f; // Alpha default
                            }
                            else if (value is float[] floatArray && floatArray.Length >= 3)
                            {
                                baseFactor[0] = floatArray[0];
                                baseFactor[1] = floatArray[1];
                                baseFactor[2] = floatArray[2];
                                baseFactor[3] = floatArray.Length >= 4 ? floatArray[3] : 1.0f;
                            }
                        }
                    }

                    var bfLin = SrgbToLinear(new Vector3(baseFactor[0], baseFactor[1], baseFactor[2]));


                    // Iterate triangles
                    int triCount = indices.Length / 3;
                    for (int ti = 0; ti < triCount; ti++)
                    {
                        var ia = (int)indices[3 * ti + 0];
                        var ib = (int)indices[3 * ti + 1];
                        var ic = (int)indices[3 * ti + 2];

                        var A = Vector3.Transform(pos[ia], world);
                        var B = Vector3.Transform(pos[ib], world);
                        var C = Vector3.Transform(pos[ic], world);

                        var uva = uvs != null ? uvs[ia] : Vector2.Zero;
                        var uvb = uvs != null ? uvs[ib] : Vector2.Zero;
                        var uvc = uvs != null ? uvs[ic] : Vector2.Zero;

                        var ca = cols != null ? new Vector3(cols[ia].X, cols[ia].Y, cols[ia].Z) : Vector3.One;
                        var cb = cols != null ? new Vector3(cols[ib].X, cols[ib].Y, cols[ib].Z) : Vector3.One;
                        var cc = cols != null ? new Vector3(cols[ic].X, cols[ic].Y, cols[ic].Z) : Vector3.One;

                        rows.Add(new Triangle(
                            meshCounter, ti,
                            A.X, A.Y, A.Z,
                            B.X, B.Y, B.Z,
                            C.X, C.Y, C.Z
                        ));
                    }
                    meshCounter++;
                }
            }

            foreach (var c in n.VisualChildren)
                Traverse(c, world);
        }
        return TransformVisualToPrinterDomain(rows);
    }
    public static List<Triangle> TransformVisualToPrinterDomain(List<Triangle> triangles)
    {
        var transformed = new List<Triangle>();

        foreach (var triangle in triangles)
        {
            // Convert from Y-up (GLTF) to Z-up (machining)
            // Mapping: 
            //   GLTF (Y-up): X=X, Y=up, Z=forward  
            //   Z-up: X=X, Y=forward, Z=up
            var transformedTriangle = new Triangle(
    triangle.MeshIndex,          // MeshIndex
    triangle.TriIndex,           // TriIndex
    -triangle.Ax, -triangle.Az, triangle.Ay,  // Ax, Ay, Az
    -triangle.Cx, -triangle.Cz, triangle.Cy,  // Bx, By, Bz  
    -triangle.Bx, -triangle.Bz, triangle.By  // Cx, Cy, Cz
);

            transformed.Add(transformedTriangle);
        }

        return transformed;
    }
    static Vector3 SrgbToLinear(Vector3 c) =>
        new Vector3(CompSrgbToLinear(c.X), CompSrgbToLinear(c.Y), CompSrgbToLinear(c.Z));

    static Vector3 LinearToSrgb(Vector3 c) =>
        new Vector3(CompLinearToSrgb(c.X), CompLinearToSrgb(c.Y), CompLinearToSrgb(c.Z));

    static float CompSrgbToLinear(float c) => (c <= 0.04045f) ? c / 12.92f : MathF.Pow((c + 0.055f) / 1.055f, 2.4f);
    static float CompLinearToSrgb(float c) => (c <= 0.0031308f) ? 12.92f * c : 1.055f * MathF.Pow(c, 1f / 2.4f) - 0.055f;

}


public class Triangle
{
    public int MeshIndex { get; set; }
    public int TriIndex { get; set; }
    public float Ax { get; set; }
    public float Ay { get; set; }
    public float Az { get; set; }
    public float Bx { get; set; }
    public float By { get; set; }
    public float Bz { get; set; }
    public float Cx { get; set; }
    public float Cy { get; set; }
    public float Cz { get; set; }

    public Triangle() { }
    public Triangle(int meshIndex, int triIndex,
        float ax, float ay, float az,
        float bx, float by, float bz,
        float cx, float cy, float cz)
    {
        MeshIndex = meshIndex;
        TriIndex = triIndex;
        Ax = ax; Ay = ay; Az = az;
        Bx = bx; By = by; Bz = bz;
        Cx = cx; Cy = cy; Cz = cz;
    }
    public Point3d A => new Point3d(Ax, Ay, Az);
    public Point3d B => new Point3d(Bx, By, Bz);
    public Point3d C => new Point3d(Cx, Cy, Cz);

    public double [] X { get => new double[] { A.X, B.X, C.X }; }
    public double[] Y { get => new double[] { A.Y, B.Y, C.Y }; }
    public double[] Z { get => new double[] { A.Z, B.Z, C.Z }; }

    public override string ToString()
    {
        return $"Tri:{A}{B}{C}";
    }

    // Keep your existing 2D normal computation
    public Vector2 ComputeOutwardNormal(char slicingAxis)
    {
        var normal3D = ComputeOutwardNormal();
        Vector2 normal2D = slicingAxis switch
        {
            'X' => new Vector2(normal3D.Y, normal3D.Z),
            'Y' => new Vector2(normal3D.X, normal3D.Z),
            'Z' => new Vector2(normal3D.X, normal3D.Y),
            _ => throw new ArgumentException("Invalid slicing axis")
        };

        normal2D = -normal2D;

        return Vector2.Normalize(normal2D);
    }

    // Keep your existing 2D normal computation
    public Vector3 ComputeOutwardNormal()
    {
        var v1 = new Vector3(Bx - Ax, By - Ay, Bz - Az);
        var v2 = new Vector3(Cx - Ax, Cy - Ay, Cz - Az);
        var normal3D = -Vector3.Cross(v1, v2);
        return Vector3.Normalize(normal3D);
    }

    internal void InvertNormal()
    {
        // Swap vertices B and C to invert the face normal
        (Bx, Cx) = (Cx, Bx);
        (By, Cy) = (Cy, By);
        (Bz, Cz) = (Cz, Bz);
    }
    /// <summary>
    /// Exports a list of Triangles to a binary STL file.
    /// </summary>
    /// <param name="triangles">The list of triangles to export.</param>
    /// <param name="filePath">The path and name of the STL file to create.</param>
    public static void CreateSTL(List<Triangle> triangles, string filePath)
    {
        if (triangles == null || triangles.Count == 0)
        {
            // Handle case where there are no triangles
            return;
        }

        try
        {
            using (var stream = new FileStream(filePath, FileMode.Create))
            using (var writer = new BinaryWriter(stream))
            {
                // 1. Write the 80-byte Header
                // You can include a file description here, or just write zeros.
                byte[] header = new byte[80];
                string description = "Exported by C# StlExporter";
                System.Text.Encoding.ASCII.GetBytes(description).CopyTo(header, 0);
                writer.Write(header);

                // 2. Write the 4-byte Triangle Count (UINT32)
                writer.Write((uint)triangles.Count);

                // 3. Write the 50-byte data for each Triangle
                foreach (var tri in triangles)
                {
                    // Convert vertex data to Vector3 for normal calculation
                    var v1 = new Vector3(tri.Ax, tri.Ay, tri.Az);
                    var v2 = new Vector3(tri.Bx, tri.By, tri.Bz);
                    var v3 = new Vector3(tri.Cx, tri.Cy, tri.Cz);

                    // Calculate the Normal Vector (Cross product and normalize)
                    // Edge1 = V2 - V1
                    var edge1 = v2 - v1;
                    // Edge2 = V3 - V1
                    var edge2 = v3 - v1;

                    // Normal = Cross(Edge1, Edge2) - use System.Numerics.Vector3.Cross
                    var normal = Vector3.Cross(edge1, edge2);

                    // Normalize the vector (make it a unit vector)
                    // The STL format expects a unit normal vector
                    if (normal.Length() > float.Epsilon)
                    {
                        normal = Vector3.Normalize(normal);
                    }
                    else
                    {
                        // Fallback: If area is zero (collinear), use a zero normal
                        normal = Vector3.Zero;
                    }

                    // --- Write Normal Vector (3 x FLOAT) ---
                    writer.Write(normal.X);
                    writer.Write(normal.Y);
                    writer.Write(normal.Z);

                    // --- Write Vertex 1 (3 x FLOAT) ---
                    writer.Write(v1.X);
                    writer.Write(v1.Y);
                    writer.Write(v1.Z);

                    // --- Write Vertex 2 (3 x FLOAT) ---
                    writer.Write(v2.X);
                    writer.Write(v2.Y);
                    writer.Write(v2.Z);

                    // --- Write Vertex 3 (3 x FLOAT) ---
                    writer.Write(v3.X);
                    writer.Write(v3.Y);
                    writer.Write(v3.Z);

                    // --- Write 2-byte Attribute Byte Count (UINT16) ---
                    writer.Write((ushort)0);
                }
            }

            // Console.WriteLine($"Successfully exported {triangles.Count} triangles to {filePath}");
        }
        catch (IOException ex)
        {
            // Handle file access/write errors
            // Console.WriteLine($"An error occurred: {ex.Message}");
        }
    }
}