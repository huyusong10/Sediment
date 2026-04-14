(function () {
  const shell = window.SedimentShell;
  const UI = shell.readJsonScript("sediment-page-data") || {};
  const { fetchJson } = shell;

  async function signIn() {
    const token = document.getElementById("admin-session-token").value.trim();
    await fetchJson("/api/admin/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    window.location.href = UI.redirect;
  }

  async function checkSession() {
    const data = await fetchJson("/api/admin/session");
    if (data.authenticated) {
      window.location.href = UI.redirect;
    }
  }

  function showError(error) {
    document.getElementById("login-status").textContent = error.message || UI.login_failed;
  }

  document.getElementById("login-button").addEventListener("click", () => signIn().catch(showError));
  document.getElementById("admin-session-token").addEventListener("keydown", (event) => {
    if (event.key === "Enter") signIn().catch(showError);
  });

  checkSession().catch(showError);
})();
