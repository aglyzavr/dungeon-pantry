document.addEventListener("click", function (e) {
  var btn = e.target.closest("[data-hp-action]");
  if (!btn) return;

  var baseUrl = btn.getAttribute("data-vitals-base-url");
  var action = btn.getAttribute("data-hp-action");
  var input = btn.closest(".hp-adjust-controls").querySelector(".hp-input");
  var val = parseInt(input.value) || 0;
  var delta = action === "heal" ? val : -val;

  htmx.ajax("POST", baseUrl + "/vitals/hp", {
    target: "#vitals-section",
    swap: "outerHTML",
    values: { delta: delta },
  });
});
