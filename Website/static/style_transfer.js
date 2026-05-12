document.addEventListener("DOMContentLoaded", function () {
    const BASE_PATH = window.ARTRECSYS_BASE_PATH || "";
    const appPath = (path) => `${BASE_PATH}${path}`;

    /* DOM references */
    const contentDrop = document.getElementById('contentDrop');
    const styleDrop = document.getElementById('styleDrop');
    const contentInput = document.getElementById('contentInput');
    const styleInput = document.getElementById('styleInput');
    const contentPreview = document.getElementById('contentPreview');
    const stylePreview = document.getElementById('stylePreview');
    const contentImg = document.getElementById('contentImg');
    const styleImg = document.getElementById('styleImg');
    const contentMeta = document.getElementById('contentMeta');
    const styleMeta = document.getElementById('styleMeta');
    const clearContent = document.getElementById('clearContent');
    const clearStyle = document.getElementById('clearStyle');
    const createBtn = document.getElementById('createBtn');
    const overlay = document.getElementById('overlay');
    const toast = document.getElementById('toast');
    const resultArea = document.getElementById('resultArea');
    const resultImg = document.getElementById('resultImg');
    const jsonArea = document.getElementById('jsonArea');
    const downloadBtn = document.getElementById('downloadBtn');

    const progressBar = document.getElementById("bar");
    const progressText = document.getElementById("progress-text");

    function updateProgressBar(percent) {
        progressBar.style.width = percent + "%";
        progressText.textContent = percent + "%";
    }

    async function pollProgress() {
        try {
            const response = await fetch(appPath("/style-transfer-progress"));

            if (!response.ok) {
                throw new Error("Progress endpoint failed");
            }

            const data = await response.json();

            console.log(data);

            updateProgressBar(data.percent);

            if (data.running) {
                setTimeout(pollProgress, 500);
            }

        } catch (err) {
            console.error("Polling error:", err);
        }
    }

    /* State */
    let contentFile = null;
    let styleFile = null;

    let latestGeneratedBlob = null;
    let latestGeneratedFilename = null;

    /* Drag & drop helpers */
    function preventDefault(e) { e.preventDefault(); e.stopPropagation(); }
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(evt => {
        contentDrop.addEventListener(evt, preventDefault, false);
        styleDrop.addEventListener(evt, preventDefault, false);
    });

    function addDragClass(el) { el.classList.add('dragover'); }
    function removeDragClass(el) { el.classList.remove('dragover'); }

    contentDrop.addEventListener('dragover', () => addDragClass(contentDrop));
    contentDrop.addEventListener('dragleave', () => removeDragClass(contentDrop));
    contentDrop.addEventListener('drop', (e) => {
        removeDragClass(contentDrop);
        const f = e.dataTransfer.files && e.dataTransfer.files[0];
        if (f) handleFile(f, 'content');
    });
    contentDrop.addEventListener('click', () => contentInput.click());
    contentInput.addEventListener('change', (e) => {
        const f = e.target.files[0];
        if (f) handleFile(f, 'content');
    });

    styleDrop.addEventListener('dragover', () => addDragClass(styleDrop));
    styleDrop.addEventListener('dragleave', () => removeDragClass(styleDrop));
    styleDrop.addEventListener('drop', (e) => {
        removeDragClass(styleDrop);
        const f = e.dataTransfer.files && e.dataTransfer.files[0];
        if (f) handleFile(f, 'style');
    });
    styleDrop.addEventListener('click', () => styleInput.click());
    styleInput.addEventListener('change', (e) => {
        const f = e.target.files[0];
        if (f) handleFile(f, 'style');
    });

    /* File handling & preview */
    function handleFile(file, type) {
        if (!file.type.startsWith('image/')) {
            alert('Please drop an image file.');
            return;
        }
        const reader = new FileReader();
        reader.onload = (ev) => {
            if (type === 'content') {
                contentFile = { file, dataUrl: ev.target.result };
                contentImg.src = ev.target.result;
                contentMeta.textContent = `${file.name} — ${Math.round(file.size / 1024)} KB`;
                contentPreview.style.display = 'flex';
            } else {
                styleFile = { file, dataUrl: ev.target.result };
                styleImg.src = ev.target.result;
                styleMeta.textContent = `${file.name} — ${Math.round(file.size / 1024)} KB`;
                stylePreview.style.display = 'flex';
            }
            updateControls();
        };
        reader.readAsDataURL(file);
    }

    clearContent.addEventListener('click', () => {
        contentFile = null;
        contentPreview.style.display = 'none';
        contentInput.value = '';
        updateControls();
    });
    clearStyle.addEventListener('click', () => {
        styleFile = null;
        stylePreview.style.display = 'none';
        styleInput.value = '';
        updateControls();
    });

    function hasCreatedArt() {
        const arr = loadCreatedArt();
        return arr && arr.length > 0;
    }

    function updateControls() {
        const ready = contentFile && styleFile;
        createBtn.disabled = !ready;
        downloadBtn.disabled = !latestGeneratedBlob;
        if (jsonArea) {
            jsonArea.style.display = hasCreatedArt() ? 'block' : 'none';

            if (hasCreatedArt()) {
                jsonArea.textContent = JSON.stringify(loadCreatedArt(), null, 2);
            }
        }
    }

    /* Loader & Toast helpers */
    function showOverlay() { overlay.classList.add('show'); overlay.setAttribute('aria-hidden', 'false'); }
    function hideOverlay() { overlay.classList.remove('show'); overlay.setAttribute('aria-hidden', 'true'); }
    function showToast(message = 'Your Image was Generated Successfully! Click button to Download', ms = 3500) {
        toast.textContent = message;
        toast.classList.add('show');
        setTimeout(() => toast.classList.remove('show'), ms);
    }

    /* Save & download helpers */
    function downloadBlob(blob, filename) {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    }

    /* Created art JSON storage
    - stored in localStorage under key: 'created_art'
    - each entry: { id, timestamp, filename, meta: {contentName, styleName, contentSize, styleSize} } */
    const ART_KEY = 'created_art';
    function loadCreatedArt() {
        try {
            const raw = localStorage.getItem(ART_KEY);
            return raw ? JSON.parse(raw) : [];
        } catch (e) { return []; }
    }

    function saveCreatedArt(arr) {
        localStorage.setItem(ART_KEY, JSON.stringify(arr));
    }

    function addCreatedArt(entry) {
        const arr = loadCreatedArt();
        arr.unshift(entry);
        saveCreatedArt(arr);
        if (jsonArea) {
            jsonArea.style.display = 'block';
            jsonArea.textContent = JSON.stringify(arr, null, 2);
        }
    }

    /* Neural Style Transfer */
    async function run_style_transfer() {
        try {
            createBtn.disabled = true;
            latestGeneratedBlob = null;
            latestGeneratedFilename = null;
            downloadBtn.disabled = true;

            // send to Flask endpoint
            const formData = new FormData();
            formData.append("content", contentFile.file);
            formData.append("style", styleFile.file);

            // Reset UI
            updateProgressBar(0);

            const responsePromise = fetch(appPath("/style-transfer"), {
                method: "POST",
                body: formData,
            });

            setTimeout(() => {
                pollProgress();
            }, 200);

            const response = await responsePromise;
            if (!response.ok) throw new Error("NST request failed");
            const result = await response.json();

            const downloadUrl = result.output;

            const blobResponse = await fetch(
                downloadUrl.startsWith("/") ? appPath(downloadUrl) : downloadUrl
            );

            const blob = await blobResponse.blob();

            latestGeneratedBlob = blob;
            latestGeneratedFilename = downloadUrl.split("/").pop();

            downloadBtn.disabled = false;

            // show toast
            showToast("Your new artwork has been created!");

            return blob;
        } catch (err) {
            console.error(err);
            showToast("Something went wrong while creating your art.");
        } finally {
            createBtn.disabled = false;
        }
    }

    /* Simple toast popup */
    function showToast(message) {
        const toast = document.createElement("div");
        toast.className = "toast";
        toast.innerText = message;
        document.body.appendChild(toast);
        setTimeout(() => toast.classList.add("show"), 100);
        setTimeout(() => {
            toast.classList.remove("show");
            setTimeout(() => toast.remove(), 500);
        }, 4000);
    }

    /* Create button */
    createBtn.addEventListener('click', async () => {
        if (!contentFile || !styleFile) return;
        showOverlay();
        createBtn.disabled = true;

        try {

            const blob = await run_style_transfer();

            // filename and download
            const filename = `stylised_${Date.now()}.png`;
            //downloadBlob(blob, filename);

            // display result preview
            const url = URL.createObjectURL(blob);
            resultImg.src = url;
            resultArea.style.display = 'block';

            // update created_art JSON
            const entry = {
                id: `art_${Date.now()}`,
                timestamp: new Date().toISOString(),
                filename,
                meta: {
                    contentName: contentFile.file.name,
                    styleName: styleFile.file.name,
                    contentSizeKB: Math.round(contentFile.file.size / 1024),
                    styleSizeKB: Math.round(styleFile.file.size / 1024)
                }
            };
            addCreatedArt(entry);

            showToast('Finished! Stylised image can be Downloaded by clicking the button below.');
        } catch (err) {
            console.error(err);
            alert('An error occurred while creating the stylised image. ');
        } finally {
            hideOverlay();
            createBtn.disabled = false;
        }
    });

    /* Download generated image */
    downloadBtn.addEventListener('click', () => {
        if (!latestGeneratedBlob) {
            return;
        }
        downloadBlob(
            latestGeneratedBlob,
            latestGeneratedFilename || `stylised_${Date.now()}.png`
        );
        showToast("Image downloaded successfully!");
    });

    /* Show stored JSON on load */
    updateControls();
});

