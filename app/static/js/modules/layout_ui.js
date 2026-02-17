/**
 * Layout & Navigation UI
 * Handles Sidebar resizing, Nav Rail switching, and Advanced Options Modal
 */
import { mapController } from './map_manager.js';

export function initLayoutUI() {
    initNavRail();
    initSidebarResize();
    initPanelCollapse();
    initAdvancedModal();
}

/**
 * Nav Rail Logic
 */
function initNavRail() {
    const navRailBtns = document.querySelectorAll(".nav-rail-btn");
    
    // Resume saved view
    const savedView = localStorage.getItem("selectedView");
    if (savedView && document.getElementById(savedView)) {
        switchView(savedView);
    }

    navRailBtns.forEach(btn => {
        btn.addEventListener("click", () => {
             const viewId = btn.dataset.view;
             if (viewId) switchView(viewId);
        });
    });
}

function switchView(viewId) {
    const navRailBtns = document.querySelectorAll(".nav-rail-btn");
    const viewPanels = document.querySelectorAll(".view-panel");
    const sidebar = document.getElementById("sidebar");

    // Update buttons
    navRailBtns.forEach(btn => {
        btn.classList.toggle("active", btn.dataset.view === viewId);
    });

    // Update panels
    viewPanels.forEach(panel => {
        const isActive = panel.id === viewId;
        panel.classList.toggle("hidden", !isActive);
        panel.dataset.active = isActive.toString();
    });

    // Mobile: open sidebar
    if (window.innerWidth < 768 && sidebar) {
        sidebar.classList.add("mobile-open");
    }

    localStorage.setItem("selectedView", viewId);
}

/**
 * Sidebar Resizing
 */
function initSidebarResize() {
    const sidebarEl = document.getElementById("sidebar");
    const resizeHandle = document.getElementById("sidebar-resize-handle");
    const MIN_WIDTH = 280;
    const MAX_WIDTH = 600;

    let isResizing = false;
    let startX = 0;
    let startWidth = 0;

    if (!resizeHandle || !sidebarEl) return;

    // Restore saved width
    const savedWidth = localStorage.getItem("sidebarWidth");
    if (savedWidth) {
        const w = parseInt(savedWidth);
        if (w >= MIN_WIDTH && w <= MAX_WIDTH) sidebarEl.style.width = `${w}px`;
    }

    resizeHandle.addEventListener("mousedown", (e) => {
        if (window.innerWidth < 768) return;
        isResizing = true;
        startX = e.clientX;
        startWidth = sidebarEl.offsetWidth;
        document.body.classList.add("resizing");
        resizeHandle.classList.add("dragging");
        
        document.addEventListener("mousemove", onMouseMove);
        document.addEventListener("mouseup", onMouseUp);
        e.preventDefault();
    });

    function onMouseMove(e) {
        if (!isResizing) return;
        const diff = e.clientX - startX;
        let newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, startWidth + diff));
        sidebarEl.style.width = `${newWidth}px`;
    }

    function onMouseUp() {
        if (!isResizing) return;
        isResizing = false;
        document.body.classList.remove("resizing");
        resizeHandle.classList.remove("dragging");
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);

        localStorage.setItem("sidebarWidth", sidebarEl.offsetWidth);
        if (mapController && mapController.map) mapController.map.invalidateSize();
    }
}

/**
 * Panel Collapse
 */
function initPanelCollapse() {
    const leftPanel = document.getElementById("left-panel");
    const collapseToggle = document.getElementById("collapse-toggle");
    const expandPanelBtn = document.getElementById("expand-panel-btn");

    if (!leftPanel || !collapseToggle) return;

    const toggle = () => {
        const isCollapsed = leftPanel.classList.toggle("collapsed");
        if (expandPanelBtn) expandPanelBtn.classList.toggle("hidden", !isCollapsed);
        localStorage.setItem("panelCollapsed", isCollapsed);
        
        setTimeout(() => {
            if (mapController && mapController.map) mapController.map.invalidateSize();
        }, 350);
    };

    collapseToggle.addEventListener("click", toggle);
    if (expandPanelBtn) expandPanelBtn.addEventListener("click", toggle);

    // Restore state
    if (localStorage.getItem("panelCollapsed") === "true") {
        leftPanel.classList.add("collapsed");
        if (expandPanelBtn) expandPanelBtn.classList.remove("hidden");
    }
}

/**
 * Advanced Options Modal
 */
function initAdvancedModal() {
    const advancedHelpBtn = document.getElementById("advanced-help-btn");
    const advancedModal = document.getElementById("advanced-options-modal");
    const closeBtns = document.querySelectorAll("#close-advanced-modal, #close-advanced-modal-btn");

    const toggleModal = (show) => {
        if (!advancedModal) return;
        advancedModal.classList.toggle("hidden", !show);
    };

    if (advancedHelpBtn) advancedHelpBtn.addEventListener("click", () => toggleModal(true));
    closeBtns.forEach(btn => btn.addEventListener("click", () => toggleModal(false)));
    
    if (advancedModal) {
        advancedModal.addEventListener("click", (e) => {
            if (e.target === advancedModal) toggleModal(false);
        });
    }
}
