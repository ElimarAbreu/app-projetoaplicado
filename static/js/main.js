// Aprimoramentos de interface; a validação de negócio também ocorre no servidor.
document.addEventListener("DOMContentLoaded", () => {
  const weight = document.querySelector("#weight");
  const height = document.querySelector("#height");
  if (weight) weight.setAttribute("aria-describedby", "weight-help");
  if (height) height.setAttribute("aria-describedby", "height-help");
});
