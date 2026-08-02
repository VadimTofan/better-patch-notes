import { mount } from "@vue/test-utils";
import { createMemoryHistory } from "vue-router";
import { describe, expect, it } from "vitest";

import App from "./App.vue";
import { createAppRouter } from "./router";

describe("public patch-note browser", () => {
  it("opens a shareable class route with all classes and channel controls", async () => {
    // Given the public Druid route
    const router = createAppRouter(createMemoryHistory());
    await router.push("/druid");
    await router.isReady();

    // When the application is mounted
    const wrapper = mount(App, {
      global: { plugins: [router] },
    });

    // Then the class browser and both channels are available
    expect(wrapper.get('[data-testid="page-title"]').text()).toContain("Druid");
    expect(wrapper.findAll('[data-testid="class-link"]')).toHaveLength(13);
    expect(wrapper.find('[data-testid="channel-live"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="channel-ptr"]').exists()).toBe(true);
  });

  it("persists a manually selected locale", async () => {
    // Given the patch-note browser
    const router = createAppRouter(createMemoryHistory());
    await router.push("/druid");
    await router.isReady();
    const wrapper = mount(App, {
      global: { plugins: [router] },
    });

    // When Russian is selected
    await wrapper.get('[data-testid="locale-select"]').setValue("ruRU");

    // Then the preference is retained in the first-party cookie
    expect(document.cookie).toContain("bpn_locale=ruRU");
  });
});
