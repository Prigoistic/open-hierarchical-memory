"use strict";
(() => {
  const params = new URLSearchParams(location.search);
  document.documentElement.classList.toggle(
    "is-embedded",
    params.get("embed") === "1",
  );
  if (location.port === "8791" && !params.has("standalone"))
    location.replace("http://127.0.0.1:8792/" + location.search);
})();
