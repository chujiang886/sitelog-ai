"use client";

import { create } from "zustand";

interface AppStore {
  isSidebarOpen: boolean;
  setSidebarOpen: (isOpen: boolean) => void;
}

/** UI-only state placeholder; domain state belongs to later feature stores. */
export const useAppStore = create<AppStore>((set) => ({
  isSidebarOpen: true,
  setSidebarOpen: (isOpen: boolean): void => set({ isSidebarOpen: isOpen }),
}));
