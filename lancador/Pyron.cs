// Lançador do Pyron: o executável da área de trabalho.
//
// Sobe o servidor local (pythonw -m app.iniciar ... --auto-encerrar) sem console, mostra uma tela de
// abertura com a logo enquanto ele carrega e abre a interface numa janela própria do Edge (modo
// aplicativo). Se o servidor já estiver no ar, só abre outra janela. O servidor se desliga sozinho
// quando a última janela é fechada, então não há nada para encerrar à mão.
//
// Compilado pelo csc.exe do .NET Framework que vem com o Windows (ver construir.py). C# 5: sem
// interpolação de texto nem operadores ?. para caber no compilador antigo.

using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

namespace Pyron
{
    static class Programa
    {
        const int PortaInicial = 8765;
        const int EsperaMaximaSegundos = 120;
        public const string Nome = "Pyron";

        public static string Projeto;
        public static string PastaDados;

        [STAThread]
        static int Main(string[] argumentos)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            Projeto = LocalizarProjeto();
            if (Projeto == null)
            {
                Erro("Não encontrei a pasta do Pyron.\n\nEsperada em:\n" + Local.Projeto +
                     "\n\nSe ela mudou de lugar, defina a variável de ambiente PYRON_PASTA ou gere o executável de novo (lancador\\construir.py).");
                return 1;
            }
            PastaDados = Path.Combine(Projeto, "app", "dados_app");

            // Dois cliques seguidos não podem subir dois servidores.
            bool criado;
            using (var trava = new Mutex(false, "Local\\Pyron.Lancador", out criado))
            {
                bool dono = false;
                try
                {
                    try { dono = trava.WaitOne(TimeSpan.FromSeconds(EsperaMaximaSegundos)); }
                    catch (AbandonedMutexException) { dono = true; }
                    if (Array.IndexOf(argumentos, "--verificar") >= 0) return Verificar();
                    return Executar();
                }
                finally
                {
                    if (dono) trava.ReleaseMutex();
                }
            }
        }

        static int Executar()
        {
            int porta = PortaSalva();
            if (porta > 0 && Responde(porta))
            {
                Avisar(porta);  // zera o relógio de desligamento enquanto a nova janela carrega
                AbrirJanela(porta);
                return 0;
            }

            string python = Path.Combine(Projeto, ".venv", "Scripts", "pythonw.exe");
            if (!File.Exists(python))
            {
                Erro("O ambiente Python do Pyron não foi encontrado:\n" + python +
                     "\n\nCrie-o na pasta do projeto seguindo o README (Instalação do zero).");
                return 1;
            }

            porta = PortaLivre();
            Process servidor;
            try
            {
                servidor = IniciarServidor(python, porta);
            }
            catch (Exception e)
            {
                Erro("Não consegui iniciar o servidor do Pyron.\n\n" + e.Message);
                return 1;
            }
            SalvarPorta(porta);

            var abertura = new Abertura(porta, servidor);
            Application.Run(abertura);
            if (!abertura.Pronto)
            {
                if (!abertura.Cancelado)
                    Erro(abertura.Motivo + "\n\nDetalhes no registro:\n" + Path.Combine(PastaDados, "servidor.log"));
                return 1;
            }
            return 0;
        }

        static Process IniciarServidor(string python, int porta)
        {
            var inicio = new ProcessStartInfo(python, "-m app.iniciar --porta " + porta + " --sem-navegador --auto-encerrar");
            inicio.WorkingDirectory = Projeto;
            inicio.UseShellExecute = false;
            inicio.CreateNoWindow = true;
            return Process.Start(inicio);
        }

        /// <summary>
        /// Teste sem interface: sobe o servidor escondido, espera responder, desenha a tela de abertura
        /// em dados_app\verificacao.png, desliga o servidor e anota o resultado em dados_app\verificacao.txt.
        /// </summary>
        static int Verificar()
        {
            var relatorio = new StringBuilder();
            var relogio = Stopwatch.StartNew();
            int codigo = 1;
            Process servidor = null;
            int porta = PortaLivre();
            try
            {
                relatorio.AppendLine("projeto: " + Projeto);
                string python = Path.Combine(Projeto, ".venv", "Scripts", "pythonw.exe");
                relatorio.AppendLine("python: " + python + (File.Exists(python) ? "" : " (NÃO ENCONTRADO)"));
                relatorio.AppendLine("edge: " + (LocalizarEdge() ?? "(não encontrado; usaria o navegador padrão)"));
                relatorio.AppendLine("porta: " + porta);
                servidor = IniciarServidor(python, porta);
                while (relogio.Elapsed.TotalSeconds < EsperaMaximaSegundos && !servidor.HasExited && !Responde(porta))
                    Thread.Sleep(250);
                bool ok = Responde(porta);
                relatorio.AppendLine("servidor respondeu: " + (ok ? "sim, em " + relogio.Elapsed.TotalSeconds.ToString("0.0") + " s" : "não"));

                Directory.CreateDirectory(PastaDados);
                using (var abertura = new Abertura(porta, servidor))
                using (var imagem = new Bitmap(abertura.ClientSize.Width, abertura.ClientSize.Height))
                {
                    abertura.DrawToBitmap(imagem, new Rectangle(Point.Empty, abertura.ClientSize));
                    imagem.Save(Path.Combine(PastaDados, "verificacao.png"), System.Drawing.Imaging.ImageFormat.Png);
                }
                codigo = ok ? 0 : 1;
            }
            catch (Exception e)
            {
                relatorio.AppendLine("erro: " + e);
            }
            finally
            {
                try
                {
                    var pedido = (HttpWebRequest)WebRequest.Create(Url(porta) + "api/encerrar");
                    pedido.Method = "POST";
                    pedido.ContentLength = 0;
                    pedido.Timeout = 1500;
                    pedido.Proxy = null;
                    using (pedido.GetResponse()) { }
                }
                catch (Exception) { }
                if (servidor != null && !servidor.WaitForExit(10000))
                {
                    try { servidor.Kill(); } catch (Exception) { }
                    relatorio.AppendLine("servidor não saiu sozinho; encerrado à força");
                }
                else if (servidor != null)
                    relatorio.AppendLine("servidor desligou sozinho: sim");
                try
                {
                    Directory.CreateDirectory(PastaDados);
                    File.WriteAllText(Path.Combine(PastaDados, "verificacao.txt"), relatorio.ToString(), Encoding.UTF8);
                }
                catch (Exception) { }
            }
            return codigo;
        }

        static string LocalizarProjeto()
        {
            var candidatos = new[]
            {
                Environment.GetEnvironmentVariable("PYRON_PASTA"),
                Path.GetDirectoryName(Application.ExecutablePath),
                Local.Projeto,
            };
            foreach (var c in candidatos)
                if (!string.IsNullOrEmpty(c) && File.Exists(Path.Combine(c, "app", "iniciar.py")))
                    return c;
            return null;
        }

        static string ArquivoPorta { get { return Path.Combine(PastaDados, "porta.txt"); } }

        static int PortaSalva()
        {
            int p;
            try { if (int.TryParse(File.ReadAllText(ArquivoPorta).Trim(), out p)) return p; }
            catch (Exception) { }
            return PortaInicial;
        }

        static void SalvarPorta(int porta)
        {
            try
            {
                Directory.CreateDirectory(PastaDados);
                File.WriteAllText(ArquivoPorta, porta.ToString());
            }
            catch (Exception) { }
        }

        static int PortaLivre()
        {
            for (int p = PortaInicial; p < PortaInicial + 30; p++)
            {
                try
                {
                    var ouvinte = new TcpListener(IPAddress.Loopback, p);
                    ouvinte.Start();
                    ouvinte.Stop();
                    return p;
                }
                catch (SocketException) { }
            }
            return PortaInicial;
        }

        public static string Url(int porta) { return "http://127.0.0.1:" + porta + "/"; }

        /// <summary>O servidor que está nesta porta é mesmo o Pyron?</summary>
        public static bool Responde(int porta)
        {
            try
            {
                var pedido = (HttpWebRequest)WebRequest.Create(Url(porta) + "api/saude");
                pedido.Timeout = 800;
                pedido.Proxy = null;
                using (var resposta = (HttpWebResponse)pedido.GetResponse())
                using (var leitor = new StreamReader(resposta.GetResponseStream(), Encoding.UTF8))
                    return resposta.StatusCode == HttpStatusCode.OK && leitor.ReadToEnd().Contains("\"" + Nome + "\"");
            }
            catch (Exception) { return false; }
        }

        static void Avisar(int porta)
        {
            try
            {
                var pedido = (HttpWebRequest)WebRequest.Create(Url(porta) + "api/sinal");
                pedido.Method = "POST";
                pedido.ContentLength = 0;
                pedido.Timeout = 800;
                pedido.Proxy = null;
                using (pedido.GetResponse()) { }
            }
            catch (Exception) { }
        }

        static string LocalizarEdge()
        {
            var caminhos = new[]
            {
                Environment.GetEnvironmentVariable("ProgramFiles(x86)") + "\\Microsoft\\Edge\\Application\\msedge.exe",
                Environment.GetEnvironmentVariable("ProgramFiles") + "\\Microsoft\\Edge\\Application\\msedge.exe",
                Environment.GetEnvironmentVariable("LOCALAPPDATA") + "\\Microsoft\\Edge\\Application\\msedge.exe",
            };
            foreach (var c in caminhos)
                if (File.Exists(c)) return c;
            try
            {
                var chave = Registry.LocalMachine.OpenSubKey("SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\msedge.exe");
                if (chave != null)
                {
                    var valor = chave.GetValue("") as string;
                    if (valor != null && File.Exists(valor)) return valor;
                }
            }
            catch (Exception) { }
            return null;
        }

        /// <summary>Janela própria, sem barra de endereço; sem Edge, o navegador padrão.</summary>
        public static void AbrirJanela(int porta)
        {
            string url = Url(porta);
            string edge = LocalizarEdge();
            if (edge == null)
            {
                Process.Start(url);
                return;
            }
            var area = Screen.PrimaryScreen.WorkingArea;
            int largura = Math.Min(1480, (int)(area.Width * 0.94));
            int altura = Math.Min(920, (int)(area.Height * 0.94));
            int x = area.Left + (area.Width - largura) / 2;
            int y = area.Top + (area.Height - altura) / 2;
            string perfil = Path.Combine(PastaDados, "janela");
            string args = "--app=" + url +
                          " --user-data-dir=\"" + perfil + "\"" +
                          " --window-size=" + largura + "," + altura +
                          " --window-position=" + x + "," + y +
                          " --no-first-run --no-default-browser-check --disable-features=Translate";
            var inicio = new ProcessStartInfo(edge, args);
            inicio.UseShellExecute = false;
            Process.Start(inicio);
        }

        public static void Erro(string texto)
        {
            MessageBox.Show(texto, Nome, MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
    }

    /// <summary>Tela de abertura: a logo, o que está carregando e uma barra em movimento.</summary>
    class Abertura : Form
    {
        // Fundo branco: a mão da logo é escura e some sobre fundo escuro.
        static readonly Color Fundo = Color.White;
        static readonly Color Borda = Color.FromArgb(0xDC, 0xE2, 0xEA);
        static readonly Color Brasa = Color.FromArgb(0xF0, 0x6A, 0x1A);
        static readonly Color Texto2 = Color.FromArgb(0x4F, 0x5A, 0x6B);
        static readonly Color Texto3 = Color.FromArgb(0x8A, 0x95, 0xA6);
        static readonly Color Trilho = Color.FromArgb(0xE9, 0xED, 0xF3);

        readonly int porta;
        readonly Process servidor;
        readonly DateTime inicio = DateTime.Now;
        readonly System.Windows.Forms.Timer quadro = new System.Windows.Forms.Timer();
        readonly float k;
        readonly Image logo;
        string estado = "Iniciando…";
        volatile bool encerrando;

        public bool Pronto, Cancelado;
        public string Motivo = "O Pyron não respondeu a tempo.";

        public Abertura(int porta, Process servidor)
        {
            this.porta = porta;
            this.servidor = servidor;
            using (var g = CreateGraphics()) k = g.DpiX / 96f;
            logo = CarregarLogo();

            Text = Programa.Nome;
            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size((int)(420 * k), (int)(372 * k));
            BackColor = Fundo;
            ShowInTaskbar = true;
            DoubleBuffered = true;
            KeyPreview = true;
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch (Exception) { }

            quadro.Interval = 16;
            quadro.Tick += delegate { AtualizarEstado(); Invalidate(); };
            KeyDown += delegate (object s, KeyEventArgs e) { if (e.KeyCode == Keys.Escape) Cancelar(); };
        }

        /// <summary>
        /// A logo vem da pasta do projeto, não de dentro do .exe: o Controle Inteligente de Aplicativos
        /// do Windows bloqueou a versão com a imagem embutida, e um lançador pequeno passa.
        /// </summary>
        static Image CarregarLogo()
        {
            try
            {
                string arquivo = Path.Combine(Programa.Projeto, "app", "estatico", "marca", "logo.png");
                if (!File.Exists(arquivo)) return null;
                using (var original = Image.FromFile(arquivo))
                    return new Bitmap(original);  // cópia: não deixa o arquivo preso
            }
            catch (Exception) { return null; }
        }

        protected override CreateParams CreateParams
        {
            get
            {
                var p = base.CreateParams;
                p.ClassStyle |= 0x20000;  // CS_DROPSHADOW: sombra discreta sob a janela sem borda
                return p;
            }
        }

        protected override void OnShown(EventArgs e)
        {
            base.OnShown(e);
            quadro.Start();
            var vigia = new Thread(Esperar);
            vigia.IsBackground = true;
            vigia.Start();
        }

        void Esperar()
        {
            while (!encerrando)
            {
                if (Programa.Responde(porta))
                {
                    NaTela(Concluir);
                    return;
                }
                bool saiu;
                try { saiu = servidor.HasExited; } catch (Exception) { saiu = false; }
                if (saiu)
                {
                    Motivo = "O servidor do Pyron fechou durante a abertura.";
                    NaTela(Close);
                    return;
                }
                if ((DateTime.Now - inicio).TotalSeconds > 120)
                {
                    NaTela(Close);
                    return;
                }
                Thread.Sleep(250);
            }
        }

        void NaTela(MethodInvoker acao)
        {
            if (encerrando) return;
            try { BeginInvoke(acao); } catch (InvalidOperationException) { }
        }

        void Concluir()
        {
            Pronto = true;
            estado = "Abrindo a janela…";
            try { Programa.AbrirJanela(porta); }
            catch (Exception e) { Pronto = false; Motivo = "Não consegui abrir a janela do aplicativo.\n\n" + e.Message; }
            // Fica um instante na tela para não haver um vazio entre a abertura e a janela do app.
            var fim = new System.Windows.Forms.Timer();
            fim.Interval = 1400;
            fim.Tick += delegate { fim.Stop(); Close(); };
            fim.Start();
        }

        void Cancelar()
        {
            Cancelado = true;
            try { if (!servidor.HasExited) servidor.Kill(); } catch (Exception) { }
            Close();
        }

        protected override void OnFormClosed(FormClosedEventArgs e)
        {
            encerrando = true;
            quadro.Stop();
            base.OnFormClosed(e);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing && logo != null) logo.Dispose();
            base.Dispose(disposing);
        }

        void AtualizarEstado()
        {
            if (Pronto) return;
            double s = (DateTime.Now - inicio).TotalSeconds;
            if (s > 20) estado = "Ainda carregando. A primeira abertura do dia é a mais lenta…";
            else if (s > 6) estado = "Preparando os detectores e a biblioteca de componentes…";
            else if (s > 1.5) estado = "Carregando o motor de análise térmica…";
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.InterpolationMode = InterpolationMode.HighQualityBicubic;
            g.PixelOffsetMode = PixelOffsetMode.HighQuality;
            g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;
            float w = ClientSize.Width, h = ClientSize.Height;

            using (var borda = new Pen(Borda, 1))
                g.DrawRectangle(borda, 0, 0, w - 1, h - 1);

            if (logo != null)
            {
                float altura = 232 * k;
                float largura = altura * logo.Width / logo.Height;
                g.DrawImage(logo, (w - largura) / 2, 30 * k, largura, altura);
            }

            using (var centro = new StringFormat { Alignment = StringAlignment.Center, Trimming = StringTrimming.EllipsisCharacter })
            using (var pequeno = new Font("Segoe UI", 9.5f))
            using (var menor = new Font("Segoe UI", 8.5f))
            using (var corTexto2 = new SolidBrush(Texto2))
            using (var corTexto3 = new SolidBrush(Texto3))
            {
                g.DrawString(estado, pequeno, corTexto2, new RectangleF(32 * k, 282 * k, w - 64 * k, 22 * k), centro);
                var dica = "Esc cancela";
                var tam = g.MeasureString(dica, menor);
                g.DrawString(dica, menor, corTexto3, w - 32 * k - tam.Width, 338 * k);
                g.DrawString("NBR 15866 · MTA · ΔT entre fases", menor, corTexto3, 32 * k, 338 * k);
            }

            // Barra indeterminada: um trecho em brasa que corre sobre o trilho.
            float x0 = 48 * k, larguraBarra = w - 96 * k, y = 314 * k, alturaBarra = 3 * k;
            using (var trilho = new SolidBrush(Trilho)) g.FillRectangle(trilho, x0, y, larguraBarra, alturaBarra);
            double t = (DateTime.Now - inicio).TotalSeconds;
            float trecho = larguraBarra * 0.28f;
            float fase = Pronto ? 1f : (float)((t * 0.55) % 1.0);
            float inicioTrecho = Pronto ? x0 : x0 - trecho + (larguraBarra + trecho) * fase;
            float fimTrecho = Pronto ? x0 + larguraBarra : inicioTrecho + trecho;
            inicioTrecho = Math.Max(inicioTrecho, x0);
            fimTrecho = Math.Min(fimTrecho, x0 + larguraBarra);
            if (fimTrecho > inicioTrecho)
                using (var brasa = new SolidBrush(Brasa)) g.FillRectangle(brasa, inicioTrecho, y, fimTrecho - inicioTrecho, alturaBarra);
        }

        // Arrastar a janela sem borda.
        protected override void OnMouseDown(MouseEventArgs e)
        {
            base.OnMouseDown(e);
            if (e.Button == MouseButtons.Left)
            {
                Capture = false;
                var m = Message.Create(Handle, 0xA1, new IntPtr(2), IntPtr.Zero);  // WM_NCLBUTTONDOWN, HTCAPTION
                WndProc(ref m);
            }
        }
    }
}
