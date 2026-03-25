using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;

public sealed class BlenderLayoutRunner
{
    public sealed record BlenderLayoutOptions(
        string BlenderExe,             // e.g. @"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
        string ScriptPath,             // e.g. @"F:\CustomStarterPack\starter_pack_card_layout.py"
        string Figure,                 // --figure
        IEnumerable<string>? Acc,      // --acc (0..3)
        double CardWidth,              // --card_width (mm)
        double CardHeight,             // --card_height (mm)
        double CardThickness,          // --card_thickness (mm)
        double UpperRatio = 0.25,      // --upper_ratio
        double MarginAccessories = 2.0,// --margin_accessories
        double MarginFigure = 4.0,     // --margin_figure
        double PaddingCard = 4.0,      // --padding_card
        double Fillet = 5.0,           // --fillet
        bool FlipHead = false,         // --flip_head
        bool AccFrontUp = false,       // --acc_front_up
        string OutDir = "",            // --outdir (required)
        string MidDir = "",            // --middir (required)
        string JobId = "run",          // --job_id
        bool SaveBlend = false,        // --save_blend
        string Title = "Starter Pack", // --title
        string Subtitle = "By M3D",    // --subtitle
        double TS = 14.0,              // --TS
        double MT = 3.0,               // --MT
        double TH = 30.0,              // --TH
        string Font = "",              // --font
        double TextExtr = 0.8,         // --text_extr
        double TextLift = -0.2,         // --text_lift
        bool DontRunBlenderForRender = false,    // Don't actually run the blender, only for debugging// add to BlenderLayoutOptions(...)
        bool DontRunBlenderForJigs = false,    // Don't actually run the blender, only for debugging// add to BlenderLayoutOptions(...)
        bool HasHole = false,             // --has_hole
        double HoleD = 3.0,               // --hole_d (mm)
        double HoleMargin = 4.0,          // --hole_margin (mm)
        string HoleCorner = "top_right",  // --hole_corner: top_right|top_left|bottom_right|bottom_left
        string ModelNameSeed = "card",         // --model_name_seed
        int renderResx = 1000,
        int renderResy = 1000,
        string JigsRequested = "",        // --jigs_requested (+Z,-Z,+X,etc.)
        double OverlapX = 3.0,
        double OverlapY = 5.0,
        double OverlapZ = 5.0,
        double InflationMargin = 0.4,
        double GridHeight = 50.0,
        double FigureTrimPercent = 0.1,
        double FigureHoleDiameter = 3.0,
        double FigureHoleLength = 5.0,
        double MagnetDiameter = 6.0,
        double MagnetHeight = 3.0
    )
    {
        public int RenderResx { get; internal set; }
        public int RenderResy { get; internal set; }
        public float HolesSpacing { get; internal set; }
    }

    // === PUBLIC API ===
    public static async Task<LayoutPayload> RunAsync(BlenderLayoutOptions opt, CancellationToken ct = default)
    {
        if (string.IsNullOrWhiteSpace(opt.OutDir))
            throw new ArgumentException("--outdir is required", nameof(opt.OutDir));
        if (string.IsNullOrWhiteSpace(opt.MidDir))
            throw new ArgumentException("--middir is required", nameof(opt.MidDir));

        Directory.CreateDirectory(opt.OutDir);
        Directory.CreateDirectory(opt.MidDir);

        // Build CLI args for Blender -> Python script -> our script args after "--"
        // Blender invocation pattern mirrors your launcher .bat
        var args = new List<string>
        {
            "--background",
            "--python", Quote(opt.ScriptPath),
            "--",
            "--figure", Quote(opt.Figure),
            "--card_width", opt.CardWidth.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--card_height", opt.CardHeight.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--card_thickness", opt.CardThickness.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--upper_ratio", opt.UpperRatio.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--margin_accessories", opt.MarginAccessories.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--margin_figure", opt.MarginFigure.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--padding_card", opt.PaddingCard.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--fillet", opt.Fillet.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--outdir", Quote(opt.OutDir),
            "--middir", Quote(opt.MidDir),
            "--job_id", Quote(opt.JobId),
            "--title", Quote(opt.Title),
            "--subtitle", Quote(opt.Subtitle),
            "--TS", opt.TS.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--MT", opt.MT.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--TH", opt.TH.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--font", Quote(opt.Font),
            "--text_extr", opt.TextExtr.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--text_lift", opt.TextLift.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--model_name_seed", opt.ModelNameSeed.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--render_resx", opt.RenderResx.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--render_resy", opt.RenderResy.ToString(System.Globalization.CultureInfo.InvariantCulture),
        };

        if (opt.Acc is not null)
        {
            var accList = opt.Acc.Where(s => !string.IsNullOrWhiteSpace(s)).Take(3).ToList();
            if (accList.Count > 0)
            {
                args.Add("--acc");
                args.AddRange(accList.Select(Quote));
            }
        }
        if (opt.FlipHead) args.Add("--flip_head");
        if (opt.AccFrontUp) args.Add("--acc_front_up");
        if (opt.SaveBlend) args.Add("--save_blend");

        args.Add("--render_resx"); args.Add(opt.renderResx.ToString(System.Globalization.CultureInfo.InvariantCulture));
        args.Add("--render_resy"); args.Add(opt.renderResy.ToString(System.Globalization.CultureInfo.InvariantCulture));

        if (opt.HasHole) args.Add("--has_hole");
        args.AddRange(new[]
        {
            "--hole_d",        opt.HoleD.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--hole_margin",   opt.HoleMargin.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--hole_corner",   Quote(string.IsNullOrWhiteSpace(opt.HoleCorner) ? "top_right" : opt.HoleCorner)
            });

        // model name seed (optional)
        if (!string.IsNullOrWhiteSpace(opt.ModelNameSeed))
        {
            args.Add("--model_name_seed");
            args.Add(Quote(opt.ModelNameSeed));
        }

        if (!string.IsNullOrWhiteSpace(opt.JigsRequested))
        {
            args.Add("--jigs_requested"); args.Add(Quote(opt.JigsRequested));
            args.Add("--overlap_x"); args.Add(opt.OverlapX.ToString(System.Globalization.CultureInfo.InvariantCulture));
            args.Add("--overlap_y"); args.Add(opt.OverlapY.ToString(System.Globalization.CultureInfo.InvariantCulture));
            args.Add("--overlap_z"); args.Add(opt.OverlapZ.ToString(System.Globalization.CultureInfo.InvariantCulture));
            args.Add("--inflation_margin"); args.Add(opt.InflationMargin.ToString(System.Globalization.CultureInfo.InvariantCulture));
            args.Add("--grid_height"); args.Add(opt.GridHeight.ToString(System.Globalization.CultureInfo.InvariantCulture));
        }

        var psi = new ProcessStartInfo
        {
            FileName = opt.BlenderExe,
            Arguments = string.Join(" ", args),
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8
        };

        using var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
        var stdout = new StringBuilder();
        var stderr = new StringBuilder();
        // Echo lines to the console as they arrive (live).
        proc.OutputDataReceived += (_, e) =>
        {
            if (e.Data is not null) Console.Out.WriteLine(e.Data);
        };
        proc.ErrorDataReceived += (_, e) =>
        {
            if (e.Data is not null) Console.Error.WriteLine(e.Data);
        };
        if (!opt.DontRunBlenderForRender)
        {
            if (!proc.Start())
                throw new InvalidOperationException("Failed to start Blender process.");

            proc.BeginOutputReadLine();
            proc.BeginErrorReadLine();

            await proc.WaitForExitAsync(ct).ConfigureAwait(false);

            if (proc.ExitCode != 0)
            {
                // Surface useful logs if Blender/script failed
                var msg = $"Blender exited with code {proc.ExitCode}.\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}";
                throw new ApplicationException(msg);
            }
        }

        // Determine the JSON path: script defaults to <outdir>/layout_<job_id>.json unless --layout was passed. :contentReference[oaicite:2]{index=2}
        var jsonPath = Path.Combine(opt.MidDir, opt.ModelNameSeed + "_layout.json");

        if (!File.Exists(jsonPath))
        {
            var msg = $"Expected JSON not found at: {jsonPath}\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}";
            throw new FileNotFoundException(msg, jsonPath);
        }

        // Parse JSON according to the sample structure (meta + items). :contentReference[oaicite:3]{index=3}
        var json = await File.ReadAllTextAsync(jsonPath, ct).ConfigureAwait(false);
        var payload = JsonSerializer.Deserialize<LayoutPayload>(json, JsonOptions)
                      ?? throw new InvalidDataException("JSON deserialized to null.");


        var tris = GLBProcessor.Parse(opt.Figure); // Touch the GLB early to surface any parsing issues before launching Blender.
        var minX = tris.Min(t => t.X.Min());
        var maxX = tris.Max(t => t.X.Max());
        var minY = tris.Min(t => t.Y.Min());
        var maxY = tris.Max(t => t.Y.Max());
        var minZ = tris.Min(t => t.Z.Min());
        var maxZ = tris.Max(t => t.Z.Max());
        var lowestTris = tris.FindAll(t => t.Y.Min() <= minY + (maxY - minY) * 0.1);
        var avgZ = lowestTris.SelectMany(t => t.Z).Average();
        var zProp = avgZ / (maxZ - minZ);



        if (!string.IsNullOrWhiteSpace(opt.JigsRequested) && payload.Meta.FigureSlotBounds != null)
        {
            var bounds = payload.Meta.FigureSlotBounds;
            if (bounds.SlotCenter != null && bounds.SlotSize != null)
            {
                var makeJigPath = Path.Combine(Path.GetDirectoryName(opt.ScriptPath) ?? "", "make_jig.py");
                var jigArgs = new List<string>
                {
                    Quote(makeJigPath),
                    "--input_glb", Quote(opt.Figure),
                    "--output_dir", Quote(opt.OutDir),
                    "--model_name_seed", Quote(opt.ModelNameSeed),
                    "--slot_center", bounds.SlotCenter.X.ToString(System.Globalization.CultureInfo.InvariantCulture), bounds.SlotCenter.Y.ToString(System.Globalization.CultureInfo.InvariantCulture), bounds.SlotCenter.Z.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    "--slot_size", bounds.SlotSize.W.ToString(System.Globalization.CultureInfo.InvariantCulture), bounds.SlotSize.H.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    "--jigs_requested", Quote(opt.JigsRequested),
                    "--overlap_x", opt.OverlapX.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    "--overlap_y", opt.OverlapY.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    "--overlap_z", opt.OverlapZ.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    "--inflation_margin", opt.InflationMargin.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    "--grid_height", opt.GridHeight.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    "--holes_z_prop", zProp.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    "--holes_spacing", opt.HolesSpacing.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    "--trim_percent", opt.FigureTrimPercent.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    "--hole_diameter", opt.FigureHoleDiameter.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    "--hole_length", opt.FigureHoleLength.ToString(System.Globalization.CultureInfo.InvariantCulture)
                };

                jigArgs.Add("--magnet_diameter"); jigArgs.Add(opt.MagnetDiameter.ToString(System.Globalization.CultureInfo.InvariantCulture));
                jigArgs.Add("--magnet_height"); jigArgs.Add(opt.MagnetHeight.ToString(System.Globalization.CultureInfo.InvariantCulture));

                // Pass card 2.5D STL and layout JSON if they exist
                var cardStlPath = Path.Combine(opt.MidDir, "card_25d.stl");
                var layoutJsonPath = Path.Combine(opt.MidDir, opt.ModelNameSeed + "_layout.json");
                if (File.Exists(cardStlPath))
                {
                    jigArgs.Add("--card_stl"); jigArgs.Add(Quote(cardStlPath));
                }
                if (File.Exists(layoutJsonPath))
                {
                    jigArgs.Add("--layout_json"); jigArgs.Add(Quote(layoutJsonPath));
                }

                var jigPsi = new ProcessStartInfo
                {
                    FileName = "python",
                    Arguments = "-u " + string.Join(" ", jigArgs),
                    UseShellExecute = false,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    CreateNoWindow = true,
                    StandardOutputEncoding = Encoding.UTF8,
                    StandardErrorEncoding = Encoding.UTF8
                };
                Console.WriteLine("Args given to jig generation script:" + jigPsi.Arguments);
                using var jigProc = new Process { StartInfo = jigPsi, EnableRaisingEvents = true };
                jigProc.OutputDataReceived += (_, e) =>
                {
                    if (e.Data is not null) Console.Out.WriteLine($"[JIG] {e.Data}");
                };
                jigProc.ErrorDataReceived += (_, e) =>
                {
                    if (e.Data is not null) Console.Error.WriteLine($"[JIG-ERR] {e.Data}");
                };

                if (!opt.DontRunBlenderForJigs)
                {
                    if (!jigProc.Start())
                        throw new InvalidOperationException("Failed to start python process for jig generation.");

                    jigProc.BeginOutputReadLine();
                    jigProc.BeginErrorReadLine();

                    await jigProc.WaitForExitAsync(ct).ConfigureAwait(false);
                    if (jigProc.ExitCode != 0)
                    {
                        var msg = $"Jig generation exited with code {jigProc.ExitCode}.";
                        throw new ApplicationException(msg);
                    }
                }
            }
        }

        return payload;
    }

    private static string Quote(string s)
        => string.IsNullOrEmpty(s) ? "\"\"" : (s.Contains(' ') || s.Contains('"') ? $"\"{s.Replace("\"", "\\\"")}\"" : s);

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        ReadCommentHandling = JsonCommentHandling.Skip,
        AllowTrailingCommas = true,
        NumberHandling = JsonNumberHandling.AllowReadingFromString
    };
}

// === JSON models (align with your script’s output schema) ===
// Sample shape: { "meta": { ... }, "items": [ { "name": "...", "center": {x,y}, "size": {w,h}, "rotation_z_deg": 0 } ] } :contentReference[oaicite:4]{index=4}

public sealed class LayoutPayload
{
    [JsonPropertyName("meta")] public Meta Meta { get; set; } = new();
    [JsonPropertyName("items")] public List<Item> Items { get; set; } = new();
}

public sealed class Meta
{
    [JsonPropertyName("job_id")] public string JobId { get; set; } = "";
    [JsonPropertyName("units")] public string Units { get; set; } = "mm";
    [JsonPropertyName("card")] public Card Card { get; set; } = new();
    [JsonPropertyName("slots")] public Slots Slots { get; set; } = new();
    [JsonPropertyName("figure_slot_bounds")] public FigureSlotBounds? FigureSlotBounds { get; set; }
}

public sealed class Card
{
    [JsonPropertyName("W")] public double W { get; set; }
    [JsonPropertyName("H")] public double H { get; set; }
    [JsonPropertyName("card_thickness")] public double CardThickness { get; set; }
    [JsonPropertyName("upper_ratio")] public double UpperRatio { get; set; }
    [JsonPropertyName("padding_card")] public double PaddingCard { get; set; }
}

public sealed class Slots
{
    [JsonPropertyName("figure")] public Size Figure { get; set; } = new();
    [JsonPropertyName("accessories")] public Size Accessories { get; set; } = new();
    [JsonPropertyName("text_strip")] public TextStrip TextStrip { get; set; } = new();
}

public sealed class Size { [JsonPropertyName("w")] public double W { get; set; } [JsonPropertyName("h")] public double H { get; set; } }
public sealed class TextStrip { [JsonPropertyName("h")] public double H { get; set; } }

public sealed class Item
{
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("center")] public XY Center { get; set; } = new();
    [JsonPropertyName("size")] public Size Size { get; set; } = new();
    [JsonPropertyName("rotation_z_deg")] public double RotationZDeg { get; set; }
}

public sealed class XY { [JsonPropertyName("x")] public double X { get; set; } [JsonPropertyName("y")] public double Y { get; set; } }

public sealed class FigureSlotBounds
{
    [JsonPropertyName("slot_center")] public XYZ? SlotCenter { get; set; }
    [JsonPropertyName("slot_size")] public Size? SlotSize { get; set; }
    [JsonPropertyName("figure_actual")] public FigureActual? FigureActual { get; set; }
}

public sealed class XYZ { [JsonPropertyName("x")] public double X { get; set; } [JsonPropertyName("y")] public double Y { get; set; } [JsonPropertyName("z")] public double Z { get; set; } }

public sealed class FigureActual
{
    [JsonPropertyName("center")] public XYZ? Center { get; set; }
    [JsonPropertyName("size")] public Size3D? Size { get; set; }
}

public sealed class Size3D { [JsonPropertyName("w")] public double W { get; set; } [JsonPropertyName("h")] public double H { get; set; } [JsonPropertyName("d")] public double D { get; set; } }
