document.querySelectorAll(".tab").forEach(btn => {
    btn.addEventListener("click", () => {

        // Remove active class from all tabs
        document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
        btn.classList.add("active");

        // Hide all tab content
        document.querySelectorAll(".tab-content").forEach(sec => sec.classList.remove("active"));

        // Show selected tab
        const target = btn.getAttribute("data-tab");
        document.getElementById(target).classList.add("active");
    });
});

