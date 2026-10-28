// Pyron · site: entrada suave das seções e formulário de contato (sem servidor: abre o e-mail pronto).
const CONTATO = "contato@pyron.com.br"; // provisório, vindo do modelo de design: trocar pelo e-mail real antes de publicar

const surgem = document.querySelectorAll(".surge");
if ("IntersectionObserver" in window) {
  const olho = new IntersectionObserver((entradas) => entradas.forEach((e) => {
    if (e.isIntersecting) { e.target.classList.add("visivel"); olho.unobserve(e.target); }
  }), { rootMargin: "0px 0px -10% 0px" });
  surgem.forEach((s) => olho.observe(s));
} else {
  surgem.forEach((s) => s.classList.add("visivel"));
}

const form = document.getElementById("form-contato");
form?.addEventListener("submit", (ev) => {
  ev.preventDefault();
  const d = Object.fromEntries(new FormData(form));
  const aviso = document.getElementById("aviso-form");
  if (!d.nome.trim() || !form.email.checkValidity() || !d.email.trim()) {
    aviso.textContent = "Preencha o nome e um e-mail válido.";
    (d.nome.trim() ? form.email : form.nome).focus();
    return;
  }
  const assunto = `Pyron: contato de ${d.nome}${d.empresa ? ` (${d.empresa})` : ""}`;
  const corpo = `${d.mensagem || ""}\n\n${d.nome} · ${d.papel}\n${d.empresa || ""}\n${d.email}`;
  window.location.href = `mailto:${CONTATO}?subject=${encodeURIComponent(assunto)}&body=${encodeURIComponent(corpo)}`;
  aviso.textContent = "Mensagem pronta no seu programa de e-mail.";
});
