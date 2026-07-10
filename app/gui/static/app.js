const menuButton = document.querySelector("[data-menu]");
const menuClose = document.querySelector("[data-menu-close]");

menuButton?.addEventListener("click", () => document.body.classList.add("menu-open"));
menuClose?.addEventListener("click", () => document.body.classList.remove("menu-open"));

const today = document.querySelector("[data-today]");
if (today) {
  today.textContent = new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short"
  }).format(new Date());
}

const dropZone = document.querySelector("[data-drop-zone]");
const fileInput = document.querySelector("[data-file-input]");
const fileName = document.querySelector("[data-file-name]");

function showFiles(files) {
  if (!files?.length || !fileName) return;
  if (files.length === 1) {
    fileName.textContent = `Selected: ${files[0].name}`;
    return;
  }
  fileName.textContent = `Selected: ${files.length} files`;
}

fileInput?.addEventListener("change", () => showFiles(fileInput.files));

if (dropZone && fileInput) {
  ["dragenter", "dragover"].forEach(eventName => {
    dropZone.addEventListener(eventName, event => {
      event.preventDefault();
      dropZone.classList.add("dragging");
    });
  });
  ["dragleave", "drop"].forEach(eventName => {
    dropZone.addEventListener(eventName, event => {
      event.preventDefault();
      dropZone.classList.remove("dragging");
    });
  });
  dropZone.addEventListener("drop", event => {
    const files = event.dataTransfer.files;
    if (!files.length) return;
    fileInput.files = files;
    showFiles(files);
  });
}

const editorItems = document.querySelector("[data-editor-items]");
const itemTemplate = document.querySelector("#item-row-template");

function renumberItems() {
  editorItems?.querySelectorAll("[data-item-row]").forEach((row, index) => {
    const number = row.querySelector(".item-index");
    if (number) number.textContent = String(index + 1).padStart(2, "0");
  });
}

document.querySelector("[data-add-item]")?.addEventListener("click", () => {
  if (!editorItems || !itemTemplate) return;
  editorItems.append(itemTemplate.content.cloneNode(true));
  renumberItems();
  editorItems.lastElementChild?.querySelector("input")?.focus();
});

editorItems?.addEventListener("click", event => {
  const button = event.target.closest("[data-remove-item]");
  if (!button) return;
  button.closest("[data-item-row]")?.remove();
  renumberItems();
});

document.querySelectorAll("[data-dialog-open]").forEach(button => {
  button.addEventListener("click", () => {
    document.getElementById(button.dataset.dialogOpen)?.showModal();
  });
});

document.querySelectorAll("[data-dialog-close]").forEach(button => {
  button.addEventListener("click", () => button.closest("dialog")?.close());
});

document.querySelectorAll("dialog").forEach(dialog => {
  dialog.addEventListener("click", event => {
    if (event.target === dialog) dialog.close();
  });
});
