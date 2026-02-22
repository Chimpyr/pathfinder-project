/**
 * Auth UI Module
 * Handles login, registration, logout, and session state display.
 */

export function initAuthUI() {
    const loginForm = document.getElementById("auth-login");
    const registerForm = document.getElementById("auth-register");
    const profilePanel = document.getElementById("auth-profile");
    const authMessage = document.getElementById("auth-message");

    if (!loginForm) return; // Guard: account-view not in DOM

    // ── Sub-view Switching ───────────────────────────────────────────
    const showRegisterBtn = document.getElementById("show-register");
    const showLoginBtn = document.getElementById("show-login");

    showRegisterBtn?.addEventListener("click", () => {
        loginForm.classList.add("hidden");
        registerForm.classList.remove("hidden");
        hideMessage();
    });

    showLoginBtn?.addEventListener("click", () => {
        registerForm.classList.add("hidden");
        loginForm.classList.remove("hidden");
        hideMessage();
    });

    // ── Login ────────────────────────────────────────────────────────
    const loginBtn = document.getElementById("login-btn");
    const loginSpinner = document.getElementById("login-spinner");

    loginBtn?.addEventListener("click", async () => {
        const email = document.getElementById("login-email").value.trim();
        const password = document.getElementById("login-password").value;

        if (!email || !password) {
            showMessage("Please enter your email and password.", "error");
            return;
        }

        setLoading(loginBtn, loginSpinner, true);
        hideMessage();

        try {
            const res = await fetch("/auth/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, password }),
            });
            const data = await res.json();

            if (res.ok) {
                showProfile(data.user);
                showMessage("Signed in successfully!", "success");
            } else {
                showMessage(data.error || "Login failed.", "error");
            }
        } catch (err) {
            showMessage("Network error. Is the server running?", "error");
        } finally {
            setLoading(loginBtn, loginSpinner, false);
        }
    });

    // ── Register ─────────────────────────────────────────────────────
    const registerBtn = document.getElementById("register-btn");
    const registerSpinner = document.getElementById("register-spinner");

    registerBtn?.addEventListener("click", async () => {
        const email = document.getElementById("register-email").value.trim();
        const password = document.getElementById("register-password").value;
        const confirm = document.getElementById("register-confirm").value;

        if (!email || !password) {
            showMessage("Please fill in all fields.", "error");
            return;
        }
        if (password !== confirm) {
            showMessage("Passwords do not match.", "error");
            return;
        }
        if (password.length < 8) {
            showMessage("Password must be at least 8 characters.", "error");
            return;
        }

        setLoading(registerBtn, registerSpinner, true);
        hideMessage();

        try {
            const res = await fetch("/auth/register", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, password }),
            });
            const data = await res.json();

            if (res.ok) {
                showProfile(data.user);
                showMessage("Account created! You're now signed in.", "success");
            } else {
                showMessage(data.error || "Registration failed.", "error");
            }
        } catch (err) {
            showMessage("Network error. Is the server running?", "error");
        } finally {
            setLoading(registerBtn, registerSpinner, false);
        }
    });

    // ── Logout ───────────────────────────────────────────────────────
    const logoutBtn = document.getElementById("logout-btn");

    logoutBtn?.addEventListener("click", async () => {
        try {
            await fetch("/auth/logout", { method: "POST" });
        } catch (_) { /* Ignore network errors on logout */ }

        showLoggedOut();
        showMessage("You have been logged out.", "success");
    });

    // ── Enter key support ────────────────────────────────────────────
    document.getElementById("login-password")?.addEventListener("keydown", (e) => {
        if (e.key === "Enter") loginBtn?.click();
    });
    document.getElementById("register-confirm")?.addEventListener("keydown", (e) => {
        if (e.key === "Enter") registerBtn?.click();
    });

    // ── Session Check (on page load) ─────────────────────────────────
    checkSession();

    // ── Helpers ──────────────────────────────────────────────────────

    async function checkSession() {
        try {
            const res = await fetch("/auth/me");
            if (res.ok) {
                const data = await res.json();
                showProfile(data.user);
            }
            // If 401, stay on login form (default state)
        } catch (_) {
            // Network error — stay on login form
        }
    }

    function showProfile(user) {
        loginForm.classList.add("hidden");
        registerForm.classList.add("hidden");
        profilePanel.classList.remove("hidden");

        document.getElementById("profile-email").textContent = user.email;
        const since = new Date(user.created_at);
        document.getElementById("profile-since").textContent =
            `Member since ${since.toLocaleDateString("en-GB", { month: "long", year: "numeric" })}`;

        document.getElementById("account-subtitle").textContent = user.email;

        // Update nav icon to indicate logged-in
        const navIcon = document.getElementById("account-nav-icon");
        if (navIcon) {
            navIcon.classList.remove("fa-user-circle");
            navIcon.classList.add("fa-user-check");
            navIcon.style.color = "var(--primary-color)";
        }

        // Fetch saved data counts
        fetchCounts();
    }

    function showLoggedOut() {
        profilePanel.classList.add("hidden");
        registerForm.classList.add("hidden");
        loginForm.classList.remove("hidden");

        document.getElementById("account-subtitle").textContent = "Sign in to save routes and pins";

        // Reset nav icon
        const navIcon = document.getElementById("account-nav-icon");
        if (navIcon) {
            navIcon.classList.remove("fa-user-check");
            navIcon.classList.add("fa-user-circle");
            navIcon.style.color = "";
        }

        // Clear form fields
        document.getElementById("login-email").value = "";
        document.getElementById("login-password").value = "";
        document.getElementById("register-email").value = "";
        document.getElementById("register-password").value = "";
        document.getElementById("register-confirm").value = "";
    }

    async function fetchCounts() {
        try {
            const [pinsRes, routesRes] = await Promise.all([
                fetch("/api/pins"),
                fetch("/api/routes"),
            ]);
            if (pinsRes.ok) {
                const pinsData = await pinsRes.json();
                document.getElementById("profile-pin-count").textContent = pinsData.pins.length;
            }
            if (routesRes.ok) {
                const routesData = await routesRes.json();
                document.getElementById("profile-route-count").textContent = routesData.routes.length;
            }
        } catch (_) {
            // Silently fail — counts will show "—"
        }
    }

    function showMessage(text, type) {
        if (!authMessage) return;
        authMessage.textContent = text;
        authMessage.classList.remove("hidden",
            "bg-red-50", "text-red-600", "border-red-200",
            "bg-green-50", "text-green-600", "border-green-200",
            "dark:bg-red-900/30", "dark:text-red-400",
            "dark:bg-green-900/30", "dark:text-green-400");

        if (type === "error") {
            authMessage.classList.add("bg-red-50", "text-red-600", "border", "border-red-200",
                "dark:bg-red-900/30", "dark:text-red-400");
        } else {
            authMessage.classList.add("bg-green-50", "text-green-600", "border", "border-green-200",
                "dark:bg-green-900/30", "dark:text-green-400");
        }
    }

    function hideMessage() {
        authMessage?.classList.add("hidden");
    }

    function setLoading(btn, spinner, loading) {
        if (btn) btn.disabled = loading;
        if (spinner) spinner.classList.toggle("hidden", !loading);
    }
}
