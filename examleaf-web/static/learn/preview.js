// The staff player (/learn/preview/<clip>/, templates/learn/preview.html): hls.js where the browser has Media Source
// Extensions, the browser's own HLS otherwise (Safari). A file, not an inline script: the CSP allows none.
(function () {
  "use strict";
  var video = document.getElementById("clip-video");
  if (!video) return;
  var levels = document.getElementById("clip-levels");
  var pick = document.getElementById("clip-pick");
  var problem = document.getElementById("clip-error");
  if (window.Hls && window.Hls.isSupported()) {
    var hls = new window.Hls({ enableWorker: false }); // its worker would be a blob: script, which the CSP refuses
    hls.on(window.Hls.Events.MANIFEST_PARSED, function (event, data) {
      levels.textContent = data.levels.map(function (level) { return level.width + "×" + level.height; }).join(", ");
      [{ label: "Auto", index: -1 }].concat(data.levels.map(function (level, index) {
        return { label: level.height + "p", index: index };
      })).forEach(function (choice) {
        var button = document.createElement("button");
        button.type = "button";
        button.textContent = choice.label;
        button.addEventListener("click", function () { hls.currentLevel = choice.index; });
        pick.appendChild(button);
      });
    });
    hls.on(window.Hls.Events.ERROR, function (event, data) {
      if (data.fatal) problem.textContent = "Playback failed: " + data.type + " (" + data.details + ").";
    });
    hls.loadSource(video.dataset.src);
    hls.attachMedia(video);
  } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
    levels.textContent = "chosen by the browser";
    video.src = video.dataset.src;
  } else {
    problem.textContent = "This browser cannot play HLS.";
  }
})();
