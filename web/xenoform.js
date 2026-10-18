import { app } from "/scripts/app.js";

app.registerExtension({
  name: "xenoform.desk",
  async setup() {
    const openDesk = () => {
      const frame = document.getElementById("xenoform-frame");
      if (frame) {
        frame.src = "/xenoform";
        return;
      }
      window.open("/xenoform", "_blank");
    };

    const menu = document.querySelector(".comfy-menu");
    if (menu && !document.getElementById("xenoform-menu")) {
      const button = document.createElement("button");
      button.id = "xenoform-menu";
      button.textContent = "Xenoform";
      button.title = "Open the Xenoform director";
      button.addEventListener("click", openDesk);
      menu.append(button);
    }

    const manager = app.extensionManager;
    if (manager && typeof manager.registerSidebarTab === "function") {
      manager.registerSidebarTab({
        id: "xenoform",
        icon: "pi pi-video",
        title: "Xenoform",
        tooltip: "Xenoform director",
        type: "custom",
        render: (el) => {
          el.style.height = "100%";
          el.style.width = "100%";
          el.innerHTML =
            '<iframe id="xenoform-frame" title="Xenoform" src="/xenoform" style="width:100%;height:100%;border:0;background:#12100e"></iframe>';
        },
      });
    }
  },
});
