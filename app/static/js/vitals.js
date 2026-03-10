document.addEventListener("click", function (e) {
  var btn = e.target.closest("[data-hp-action]");
  if (!btn) return;

  var charId = btn.getAttribute("data-character-id");
  var action = btn.getAttribute("data-hp-action");
  var input = document.getElementById("hp-input-" + charId);
  var val = parseInt(input.value) || 0;
  var delta = action === "heal" ? val : -val;

  htmx.ajax("POST", "/characters/" + charId + "/vitals/hp", {
    target: "#vitals-section",
    swap: "outerHTML",
    values: { delta: delta },
  });
});
