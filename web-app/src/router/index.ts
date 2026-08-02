import { createRouter, createWebHistory, type RouterHistory } from "vue-router";

import { classSlugs, type ClassSlug } from "@/domain/classes.type";
import PatchNotesView from "@/views/PatchNotesView.vue";

function rememberedClass(): ClassSlug {
  const storedClass = localStorage.getItem("bpn_last_class");

  if (classSlugs.includes(storedClass as ClassSlug)) {
    return storedClass as ClassSlug;
  }

  return "druid";
}

export function createAppRouter(history: RouterHistory = createWebHistory()) {
  const router = createRouter({
    history,
    routes: [
      {
        path: "/",
        redirect: () => `/${rememberedClass()}`,
      },
      {
        path: "/:classSlug",
        name: "class-notes",
        component: PatchNotesView,
        beforeEnter: (to) => {
          if (!classSlugs.includes(to.params.classSlug as ClassSlug)) {
            return `/${rememberedClass()}`;
          }

          return true;
        },
      },
      {
        path: "/:pathMatch(.*)*",
        redirect: () => `/${rememberedClass()}`,
      },
    ],
    scrollBehavior: () => ({ top: 0 }),
  });

  return router;
}

export const router = createAppRouter();
