// Janela própria do Pyron: o WebView2 (motor do Edge que vem com o Windows) dentro de uma janela sem a barra
// de título do Windows. A faixa do topo da interface faz o papel dela: arrastar move a janela, dois cliques
// maximizam, e os botões de minimizar, maximizar e fechar são da própria interface (mensagens "janela:...").
// As bordas continuam do Windows: redimensionar, encaixar nas laterais, sombra e cantos arredondados.
//
// As DLLs do WebView2 (assinadas pela Microsoft) ficam em lancador\webview2 e são carregadas de lá: nada
// embutido no .exe. Sem elas, ou sem o runtime do WebView2, o lançador volta à janela do Edge (--app).

using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace Pyron
{
    class Janela : Form
    {
        readonly WebView2 web = new WebView2();
        readonly Uri endereco;
        bool fechando, podeFechar;

        /// <summary>Disparado quando a interface terminou de carregar (a abertura pode sair).</summary>
        public event EventHandler Pronta;
        /// <summary>Disparado se o WebView2 não iniciar: o lançador abre a janela do Edge no lugar.</summary>
        public event EventHandler Falhou;

        static string PastaDlls { get { return Path.Combine(Programa.Projeto, "lancador", "webview2"); } }

        /// <summary>As DLLs estão na pasta e o runtime do WebView2 está instalado.</summary>
        public static bool Disponivel()
        {
            try
            {
                if (!File.Exists(Path.Combine(PastaDlls, "WebView2Loader.dll"))) return false;
                CoreWebView2Environment.SetLoaderDllFolderPath(PastaDlls);
                return !string.IsNullOrEmpty(CoreWebView2Environment.GetAvailableBrowserVersionString());
            }
            catch (Exception) { return false; }
        }

        public Janela(int porta)
        {
            endereco = new Uri(Programa.Url(porta));
            Text = Programa.Nome;
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch (Exception) { }
            BackColor = Color.White;
            StartPosition = FormStartPosition.CenterScreen;
            var area = Screen.PrimaryScreen.WorkingArea;
            Size = new Size((int)(area.Width * 0.8), (int)(area.Height * 0.85));
            MinimumSize = new Size(800, 560);
            // Maximizada só ao aparecer (Mostrar): criada já maximizada, o Windows guardava o tamanho cheio também
            // como o tamanho "restaurado", e o botão Restaurar não mudava nada.

            web.Dock = DockStyle.Fill;
            web.DefaultBackgroundColor = Color.White;
            web.CreationProperties = new CoreWebView2CreationProperties { UserDataFolder = Path.Combine(Programa.PastaDados, "webview2") };
            web.CoreWebView2InitializationCompleted += Iniciado;
            web.NavigationCompleted += delegate (object s, CoreWebView2NavigationCompletedEventArgs e)
            {
                if (podeFechar) { Close(); return; }  // a página saiu (avisou o servidor): agora fecha
                if (Pronta != null) { var p = Pronta; Pronta = null; p(this, EventArgs.Empty); }
                AvisarEstado();
            };
            Controls.Add(web);
        }

        public void Mostrar()
        {
            WindowState = FormWindowState.Maximized;
            Show();
            Activate();
        }

        /// <summary>Começa a carregar sem mostrar a janela (ela aparece quando a interface estiver pronta).</summary>
        public void Carregar()
        {
            CreateHandle();
            web.Source = endereco;
        }

        void Iniciado(object s, CoreWebView2InitializationCompletedEventArgs e)
        {
            if (!e.IsSuccess)
            {
                if (Falhou != null) Falhou(this, EventArgs.Empty);
                return;
            }
            var cfg = web.CoreWebView2.Settings;
            cfg.IsNonClientRegionSupportEnabled = true;  // CSS app-region: drag no topo move a janela
            cfg.AreDevToolsEnabled = false;
            cfg.IsStatusBarEnabled = false;
            cfg.IsGeneralAutofillEnabled = false;
            cfg.IsPasswordAutosaveEnabled = false;
            web.CoreWebView2.DocumentTitleChanged += delegate { Text = web.CoreWebView2.DocumentTitle; };
            web.CoreWebView2.WebMessageReceived += Mensagem;
            // Menu do botão direito do navegador (Voltar, Inspecionar...) só em campo de texto (copiar e colar).
            web.CoreWebView2.ContextMenuRequested += delegate (object o, CoreWebView2ContextMenuRequestedEventArgs a)
            {
                if (!a.ContextMenuTarget.IsEditable) a.Handled = true;
            };
            // Endereço de fora (WhatsApp, documentação) abre no navegador do usuário; os do Pyron, numa janela à parte.
            web.CoreWebView2.NewWindowRequested += delegate (object o, CoreWebView2NewWindowRequestedEventArgs a)
            {
                Uri destino;
                if (Uri.TryCreate(a.Uri, UriKind.Absolute, out destino) && !destino.IsLoopback)
                {
                    a.Handled = true;
                    try { Process.Start(new ProcessStartInfo(destino.AbsoluteUri) { UseShellExecute = true }); } catch (Exception) { }
                }
            };
        }

        void Mensagem(object s, CoreWebView2WebMessageReceivedEventArgs e)
        {
            string texto;
            try { texto = e.TryGetWebMessageAsString(); } catch (Exception) { return; }
            if (texto == "janela:minimizar") WindowState = FormWindowState.Minimized;
            else if (texto == "janela:maximizar") WindowState = WindowState == FormWindowState.Maximized ? FormWindowState.Normal : FormWindowState.Maximized;
            else if (texto == "janela:fechar") Close();
            else if (texto == "janela:estado") AvisarEstado();
        }

        void AvisarEstado()
        {
            if (web.CoreWebView2 == null) return;
            try { web.CoreWebView2.PostWebMessageAsString(WindowState == FormWindowState.Maximized ? "janela:maximizada" : "janela:normal"); }
            catch (Exception) { }
        }

        protected override void OnResize(EventArgs e)
        {
            base.OnResize(e);
            AvisarEstado();
        }

        // Ao fechar, a página sai primeiro (ela avisa o servidor que a janela fechou) e só então a janela some.
        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (!podeFechar && web.CoreWebView2 != null && !fechando)
            {
                fechando = true;
                e.Cancel = true;
                Hide();
                podeFechar = true;
                web.CoreWebView2.Navigate("about:blank");
                var limite = new Timer { Interval = 1500 };
                limite.Tick += delegate { limite.Stop(); if (!IsDisposed) Close(); };
                limite.Start();
                return;
            }
            base.OnFormClosing(e);
        }

        // ---------------------------------------------------------------- sem a barra de título do Windows

        [StructLayout(LayoutKind.Sequential)] struct Retangulo { public int Esq, Topo, Dir, Base; }
        [StructLayout(LayoutKind.Sequential)] struct CalculoArea { public Retangulo R0, R1, R2; public IntPtr Posicao; }
        [DllImport("user32.dll")] static extern bool IsZoomed(IntPtr h);
        [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr h, IntPtr depois, int x, int y, int l, int a, uint flags);

        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            SetWindowPos(Handle, IntPtr.Zero, 0, 0, 0, 0, 0x0027);  // SWP_FRAMECHANGED | NOMOVE | NOSIZE | NOZORDER
        }

        protected override void WndProc(ref Message m)
        {
            // WM_NCCALCSIZE: o Windows calcula a área com bordas e barra; a barra (o topo) volta para a área da
            // janela, e as bordas dos lados e de baixo ficam (redimensionar, sombra). Maximizada, a janela passa
            // da tela pela espessura da borda: desconta essa parte em cima para nada ficar escondido.
            if (m.Msg == 0x0083 && m.WParam != IntPtr.Zero)
            {
                var antes = (CalculoArea)Marshal.PtrToStructure(m.LParam, typeof(CalculoArea));
                int topo = antes.R0.Topo;
                base.WndProc(ref m);
                var depois = (CalculoArea)Marshal.PtrToStructure(m.LParam, typeof(CalculoArea));
                // a borda é a mesma dos lados (o Windows acabou de descontá-la à esquerda); IsZoomed porque, durante a
                // maximização, o WindowState do WinForms ainda não mudou
                depois.R0.Topo = topo + (IsZoomed(Handle) ? depois.R0.Esq - antes.R0.Esq : 0);
                Marshal.StructureToPtr(depois, m.LParam, false);
                m.Result = IntPtr.Zero;
                return;
            }
            base.WndProc(ref m);
        }
    }
}
