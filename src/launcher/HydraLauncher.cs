using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using System.Runtime.InteropServices;

// Windows Common Item Dialog: Explorer navigation, address bar and folder selection.
internal static class NativeFolderPicker
{
    [ComImport, Guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")]
    class FileOpenDialog { }
    [ComImport, Guid("42F85136-DB7E-439C-85F1-E4075D135FC8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IFileDialog {
        [PreserveSig] int Show(IntPtr owner);
        void SetFileTypes(uint count, IntPtr filters);
        void SetFileTypeIndex(uint index);
        void GetFileTypeIndex(out uint index);
        void Advise(IntPtr events, out uint cookie);
        void Unadvise(uint cookie);
        void SetOptions(uint options);
        void GetOptions(out uint options);
        void SetDefaultFolder(IShellItem folder);
        void SetFolder(IShellItem folder);
        void GetFolder(out IShellItem folder);
        void GetCurrentSelection(out IShellItem item);
        void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string name);
        void GetFileName(out IntPtr name);
        void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string title);
        void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string text);
        void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string text);
        void GetResult(out IShellItem result);
        void AddPlace(IShellItem item, uint placement);
        void SetDefaultExtension([MarshalAs(UnmanagedType.LPWStr)] string extension);
        void Close(int result);
        void SetClientGuid(ref Guid guid);
        void ClearClientData();
        void SetFilter(IntPtr filter);
    }
    [ComImport, Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IShellItem {
        void BindToHandler(IntPtr context, ref Guid handler, ref Guid iid, out IntPtr result);
        void GetParent(out IShellItem parent);
        void GetDisplayName(uint format, out IntPtr name);
        void GetAttributes(uint mask, out uint attributes);
        void Compare(IShellItem item, uint hint, out int order);
    }
    public static string Choose(IntPtr owner) {
        IFileDialog dialog = (IFileDialog)new FileOpenDialog();
        IShellItem result = null;
        IntPtr path = IntPtr.Zero;
        try {
            // PICKFOLDERS | FORCEFILESYSTEM | PATHMUSTEXIST | NOCHANGEDIR | DONTADDTORECENT.
            dialog.SetOptions(0x20 | 0x40 | 0x800 | 0x8 | 0x02000000);
            dialog.SetTitle("Escolha a pasta do seu projeto");
            dialog.SetOkButtonLabel("Selecionar pasta");
            int status = dialog.Show(owner);
            if (status == unchecked((int)0x800704C7)) return null;
            Marshal.ThrowExceptionForHR(status);
            dialog.GetResult(out result);
            result.GetDisplayName(0x80058000, out path); // SIGDN_FILESYSPATH
            return Marshal.PtrToStringUni(path);
        } finally {
            if (path != IntPtr.Zero) Marshal.FreeCoTaskMem(path);
            if (result != null) Marshal.FinalReleaseComObject(result);
            Marshal.FinalReleaseComObject(dialog);
        }
    }
}

// Local checkout launcher. The access credential exists only in process memory/environment.
internal sealed class HydraLauncher : Form
{
    static readonly Regex TicketNoncePattern = new Regex("\"(?:nonce|ticket|bootstrap_nonce)\"\\s*:\\s*\"([^\"]+)\"", RegexOptions.Compiled);
    static readonly string[] FrontendRootInputs = new string[] {
        "index.html",
        "package.json",
        "vite.config.ts",
        "tailwind.config.js",
        "postcss.config.js"
    };

    readonly string root;
    int port;
    readonly bool chooseFreePort;
    readonly Label state = new Label();
    readonly Button start = new Button();
    readonly Button stop = new Button();
    readonly Button open = new Button();
    readonly HttpClient http = new HttpClient(new HttpClientHandler { UseProxy = false });
    Process backend;
    string credential;
    string backendError = "";
    bool closing;
    string testRuntime;
    string Url { get { return "http://127.0.0.1:" + port; } }

    HydraLauncher(string projectRoot, int serverPort, bool autoPort)
    {
        root = projectRoot; port = serverPort; chooseFreePort = autoPort;
        Text = "Hydra"; ClientSize = new Size(540, 320); StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.FromArgb(20,20,20); ForeColor = Color.FromArgb(232,232,232);
        Font = new Font("Segoe UI", 11); FormBorderStyle = FormBorderStyle.FixedSingle; MaximizeBox = false;
        var title = new Label { Text = "Hydra", Font = new Font("Segoe UI", 27, FontStyle.Bold), Location = new Point(26,22), AutoSize = true, ForeColor = ForeColor };
        var subtitle = new Label { Text = "Seu espaço de trabalho, em um clique.", Location = new Point(29,83), AutoSize = true, ForeColor = Color.LightGray };
        state.SetBounds(29,123,480,52); state.Text = "Sistema parado"; state.ForeColor = Color.LightGray;
        ConfigureButton(start, "Iniciar", 29, 185); ConfigureButton(stop, "Parar", 194, 185); ConfigureButton(open, "Abrir Hydra", 359, 185);
        stop.Enabled = false; open.Enabled = false;
        var note = new Label { Text = "Parar ou fechar esta janela encerra os agentes e terminais\nabertos por este executável. Seus históricos ficam salvos.", Location = new Point(29,251), Size = new Size(480,48), Font = new Font("Segoe UI", 9), ForeColor = Color.LightGray };
        Controls.AddRange(new Control[] { title, subtitle, state, start, stop, open, note });
        http.Timeout = TimeSpan.FromSeconds(4);
        start.Click += async delegate { try { await StartSystem(true); } catch (Exception e) { ShowError(e); } RefreshButtons(); };
        stop.Click += async delegate { try { await StopSystem(); } catch (Exception e) { ShowError(e); } RefreshButtons(); };
        open.Click += async delegate { try { await OpenBrowser(); } catch (Exception e) { ShowError(e); } };
        FormClosing += async delegate(object sender, FormClosingEventArgs e) {
            if (closing || backend == null || backend.HasExited) return;
            e.Cancel = true;
            try { await StopSystem(); } catch { KillOwnedBackend(); }
            closing = true; Close();
        };
    }

    void ConfigureButton(Button button, string label, int x, int y)
    {
        button.Text = label; button.SetBounds(x,y,151,45); button.FlatStyle = FlatStyle.Flat;
        button.BackColor = Color.FromArgb(40,40,40); button.ForeColor = ForeColor;
        button.FlatAppearance.BorderColor = Color.FromArgb(110,110,110); button.Cursor = Cursors.Hand;
    }

    void RefreshButtons()
    {
        bool running = backend != null && !backend.HasExited;
        start.Enabled = !running; stop.Enabled = running; open.Enabled = running;
    }

    void ShowError(Exception e)
    {
        state.Text = e.Message;
        MessageBox.Show(this, e.Message, "Hydra", MessageBoxButtons.OK, MessageBoxIcon.Information);
    }

    static string Tool(string name)
    {
        foreach (string directory in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator)) {
            try { string candidate = Path.Combine(directory.Trim('"'), name); if (File.Exists(candidate)) return candidate; } catch { }
        }
        throw new InvalidOperationException(name + " não foi encontrado. Confira a preparação do projeto no manual do Hydra.");
    }

    ProcessStartInfo Info(string executable, string arguments, string directory)
    {
        return new ProcessStartInfo(executable, arguments) { WorkingDirectory = directory, UseShellExecute = false, CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden, RedirectStandardOutput = true, RedirectStandardError = true };
    }

    async Task RunBuild(string executable, string arguments)
    {
        using (var process = Process.Start(Info(executable, arguments, Path.Combine(root,"frontend")))) {
            var output = process.StandardOutput.ReadToEndAsync();
            var error = process.StandardError.ReadToEndAsync();
            await Task.Run(() => process.WaitForExit());
            string detail = await error; await output;
            if (process.ExitCode != 0) throw new InvalidOperationException("Não foi possível preparar a interface. " + detail.Substring(0, Math.Min(detail.Length, 700)));
        }
    }

    async Task EnsureBuild()
    {
        string front = Path.Combine(root, "frontend");
        string index = Path.Combine(front, "dist", "index.html");
        DateTime newest = DateTime.MinValue;
        string srcDir = Path.Combine(front, "src");
        if (Directory.Exists(srcDir)) {
            string[] srcFiles = Directory.GetFiles(srcDir, "*", SearchOption.AllDirectories);
            for (int i = 0; i < srcFiles.Length; i++) {
                DateTime written = File.GetLastWriteTimeUtc(srcFiles[i]);
                if (written > newest) newest = written;
            }
        }
        for (int i = 0; i < FrontendRootInputs.Length; i++) {
            string configPath = Path.Combine(front, FrontendRootInputs[i]);
            if (File.Exists(configPath)) {
                DateTime written = File.GetLastWriteTimeUtc(configPath);
                if (written > newest) newest = written;
            }
        }
        if (File.Exists(index) && File.GetLastWriteTimeUtc(index) >= newest) return;
        if (!File.Exists(Path.Combine(front,"node_modules","vite","bin","vite.js"))) throw new InvalidOperationException("Falta a preparação inicial da interface: execute npm ci na pasta frontend.");
        state.Text = "Preparando a interface…";
        string node = Tool("node.exe");
        await RunBuild(node,"node_modules/typescript/bin/tsc --noEmit");
        await RunBuild(node,"node_modules/vite/bin/vite.js build");
    }

    async Task StartSystem(bool showBrowser)
    {
        if (backend != null && !backend.HasExited) { if (showBrowser) await OpenBrowser(); return; }
        start.Enabled = false;
        for (int candidate=0; candidate<11; candidate++) {
            bool busy = false;
            using (var probe = new TcpClient()) {
                try { await probe.ConnectAsync("127.0.0.1",port); busy=true; }
                catch (SocketException) { }
            }
            if (!busy) break;
            if (!chooseFreePort || candidate==10) throw new InvalidOperationException("A porta " + port + " está em uso. O Hydra preservou o processo existente; escolha uma porta livre.");
            port++;
        }
        await EnsureBuild();
        state.Text = "Iniciando o Hydra…";
        byte[] bytes = new byte[32]; using (var random = RandomNumberGenerator.Create()) random.GetBytes(bytes);
        credential = Convert.ToBase64String(bytes);
        string python = Path.Combine(root,".venv","Scripts","python.exe");
        if (!File.Exists(python)) python = Tool("python.exe");
        var info = Info(python, "-m hydra_orch.desktop_backend --port " + port + (testRuntime == null ? "" : " --runtime-dir \"" + testRuntime + "\""), root);
        info.EnvironmentVariables["PYTHONPATH"] = Path.Combine(root,"src");
        info.EnvironmentVariables["HYDRA_LOCAL_DESKTOP"] = "1";
        info.EnvironmentVariables["HYDRA_LAUNCHER_EXE"] = System.Reflection.Assembly.GetExecutingAssembly().Location;
        info.EnvironmentVariables["HYDRA_API_TOKEN"] = credential;
        info.EnvironmentVariables.Remove("HYDRA_API_TOKEN_HASH");
        info.EnvironmentVariables["HYDRA_CORS_ALLOW_ORIGINS"] = "[\"" + Url + "\",\"http://localhost:" + port + "\"]";
        backendError = "";
        backend = Process.Start(info);
        backend.OutputDataReceived += delegate { };
        backend.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e) { if (e.Data != null && backendError.Length < 3000) backendError += e.Data + "\n"; };
        backend.BeginOutputReadLine(); backend.BeginErrorReadLine();
        bool ready = false;
        for (int i=0; i<100; i++) {
            if (backend.HasExited) throw new InvalidOperationException("O servidor não iniciou. " + backendError);
            try {
                using (var message = new HttpRequestMessage(HttpMethod.Get,Url+"/v1/launcher/ping")) {
                    message.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer",credential);
                    using (var response = await http.SendAsync(message)) { if (response.IsSuccessStatusCode) { ready=true; break; } }
                }
            } catch (HttpRequestException) { } catch (TaskCanceledException) { }
            await Task.Delay(400);
        }
        if (!ready) { await StopSystem(); throw new InvalidOperationException("O Hydra demorou para iniciar. Tente novamente."); }
        state.Text = "Sistema em execução\n" + Url;
        RefreshButtons();
        if (showBrowser) await OpenBrowser();
    }

    async Task OpenBrowser()
    {
        string targetUrl = Url;
        if (!string.IsNullOrEmpty(credential)) {
            try {
                using (var request = new HttpRequestMessage(HttpMethod.Post, Url + "/v1/launcher/ticket")) {
                    request.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", credential);
                    request.Headers.Add("X-Hydra-Desktop", "1");
                    using (var response = await http.SendAsync(request)) {
                        if (response.IsSuccessStatusCode) {
                            string body = await response.Content.ReadAsStringAsync();
                            Match match = TicketNoncePattern.Match(body ?? "");
                            if (match.Success && !string.IsNullOrWhiteSpace(match.Groups[1].Value)) {
                                targetUrl = Url + "/#bootstrap_nonce=" + Uri.EscapeDataString(match.Groups[1].Value);
                            }
                        }
                    }
                }
            } catch (HttpRequestException) { } catch (TaskCanceledException) { } catch (ObjectDisposedException) { }
        }
        Process.Start(new ProcessStartInfo(targetUrl) { UseShellExecute = true });
    }

    void SavePreview(string target)
    {
        using (var image = new Bitmap(Width,Height)) { DrawToBitmap(image,new Rectangle(0,0,Width,Height)); image.Save(target,System.Drawing.Imaging.ImageFormat.Png); }
    }

    void KillOwnedBackend()
    {
        if (backend == null || backend.HasExited) return;
        using (var killer = Process.Start(new ProcessStartInfo("taskkill.exe", "/PID " + backend.Id + " /T /F") { UseShellExecute=false,CreateNoWindow=true,WindowStyle=ProcessWindowStyle.Hidden })) killer.WaitForExit(5000);
    }

    async Task StopSystem()
    {
        stop.Enabled = false; open.Enabled = false; state.Text = "Parando agentes e terminais…";
        if (backend != null && !backend.HasExited) {
            try {
                using (var request = new HttpRequestMessage(HttpMethod.Post,Url+"/v1/launcher/stop")) {
                    request.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer",credential);
                    using (var response = await http.SendAsync(request)) { }
                }
            } catch (HttpRequestException) { } catch (TaskCanceledException) { }
            for (int i=0;i<80 && !backend.HasExited;i++) await Task.Delay(150);
            KillOwnedBackend();
        }
        credential = null; state.Text = "Sistema parado"; RefreshButtons();
    }

    static string FindRoot(string[] args)
    {
        if (args != null) {
            int option = Array.IndexOf(args, "--root");
            if (option >= 0) {
                if (option + 1 >= args.Length || string.IsNullOrWhiteSpace(args[option + 1]))
                    throw new ArgumentException("Informe o caminho da pasta após --root.");
                return Path.GetFullPath(args[option + 1]);
            }
        }
        var directory = new DirectoryInfo(AppDomain.CurrentDomain.BaseDirectory);
        while (directory != null) { if (File.Exists(Path.Combine(directory.FullName,"src","hydra_orch","server.py")) && File.Exists(Path.Combine(directory.FullName,"pyproject.toml"))) return directory.FullName; directory=directory.Parent; }
        throw new InvalidOperationException("Mantenha o executável dentro da pasta do projeto Hydra.");
    }

    [STAThread]
    static int Main(string[] args)
    {
        if (args == null) args = new string[0];
        bool headlessMode = Array.IndexOf(args, "--smoke") >= 0 || Array.IndexOf(args, "--render") >= 0;
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        try {
            if (Array.IndexOf(args,"--pick-folder") >= 0) {
                // Keep the modal owner in this helper process. A foreign launcher
                // owner can remain disabled if the picker is terminated on timeout.
                using (var owner = new Form { Text="Hydra — Selecionar pasta", ShowInTaskbar=true,
                    StartPosition=FormStartPosition.CenterScreen, FormBorderStyle=FormBorderStyle.FixedDialog,
                    MaximizeBox=false, MinimizeBox=false, ClientSize=new Size(420,90),
                    BackColor=Color.FromArgb(20,20,20), ForeColor=Color.FromArgb(232,232,232) }) {
                    owner.Controls.Add(new Label { Text="Escolha a pasta na janela do Windows.",
                        Dock=DockStyle.Fill, TextAlign=ContentAlignment.MiddleCenter });
                    owner.Show(); owner.Activate();
                    string selected = NativeFolderPicker.Choose(owner.Handle);
                    if (selected != null) {
                        byte[] pathBytes=Encoding.UTF8.GetBytes(selected);
                        using (var output=Console.OpenStandardOutput()) output.Write(pathBytes,0,pathBytes.Length);
                    }
                    owner.Close();
                }
                return 0;
            }
            string root = FindRoot(args);
            int port = 8000;
            int portOption = Array.IndexOf(args, "--port");
            if (portOption >= 0) {
                if (portOption + 1 >= args.Length || !int.TryParse(args[portOption + 1], out port))
                    throw new ArgumentException("Porta inválida.");
            }
            if (port < 1024 || port > 65535) throw new ArgumentException("Porta inválida.");

            int render = Array.IndexOf(args, "--render");
            if (render >= 0 && (render + 1 >= args.Length || string.IsNullOrWhiteSpace(args[render + 1])))
                throw new ArgumentException("Informe o arquivo de destino após --render.");

            int smoke = Array.IndexOf(args, "--smoke");
            if (smoke >= 0 && (smoke + 1 >= args.Length || string.IsNullOrWhiteSpace(args[smoke + 1])))
                throw new ArgumentException("Informe o arquivo de relatório após --smoke.");

            int hold = Array.IndexOf(args, "--hold");
            int holdSeconds = 0;
            if (hold >= 0) {
                if (hold + 1 >= args.Length || !int.TryParse(args[hold + 1], out holdSeconds) || holdSeconds < 0)
                    throw new ArgumentException("Tempo de espera inválido para --hold.");
            }

            using (var form = new HydraLauncher(root, port, portOption < 0 || Array.IndexOf(args,"--auto-port") >= 0)) {
                if (render >= 0 && smoke < 0) {
                    string renderTarget = args[render + 1];
                    form.Opacity=0; form.ShowInTaskbar=false;
                    form.Shown += delegate { form.SavePreview(renderTarget); form.closing=true; form.Close(); };
                    Application.Run(form); return 0;
                }
                if (smoke >= 0) {
                    string report = Path.GetFullPath(args[smoke + 1]);
                    string reportDir = Path.GetDirectoryName(report) ?? root;
                    form.testRuntime = Path.Combine(reportDir, "runtime-" + Guid.NewGuid().ToString("N"));
                    int result = 0; form.Opacity = 0; form.ShowInTaskbar = false;
                    form.Shown += async delegate {
                        try {
                            if (render >= 0) form.SavePreview(args[render + 1]);
                            await form.StartSystem(false);
                            File.WriteAllText(report,"{\"started\":true,\"stopped\":false,\"port\":" + form.port + "}");
                            if (hold >= 0 && holdSeconds > 0) await Task.Delay(holdSeconds * 1000);
                            await form.StopSystem(); File.WriteAllText(report,"{\"started\":true,\"stopped\":true,\"port\":" + form.port + "}");
                        } catch (Exception e) { form.KillOwnedBackend(); File.WriteAllText(report,e.Message); result=1; }
                        finally { form.closing=true; form.Close(); }
                    };
                    Application.Run(form); return result;
                }
                bool created;
                string key;
                using (var sha=SHA256.Create()) key=Convert.ToBase64String(sha.ComputeHash(Encoding.UTF8.GetBytes(root))).Replace('/','_');
                using (var mutex=new Mutex(true,"Local\\Hydra_"+key,out created)) {
                    if (!created) { MessageBox.Show("O controle do Hydra já está aberto.","Hydra"); return 0; }
                    if (Array.IndexOf(args,"--start") >= 0) form.Shown += async delegate { try { await form.StartSystem(true); } catch (Exception e) { form.ShowError(e); form.RefreshButtons(); } };
                    Application.Run(form); mutex.ReleaseMutex();
                }
            }
            return 0;
        } catch (Exception e) {
            if (headlessMode) Console.Error.WriteLine(e.Message);
            else MessageBox.Show(e.Message,"Hydra",MessageBoxButtons.OK,MessageBoxIcon.Information);
            return 1;
        }
    }
}
