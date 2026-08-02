import { afterEach } from "vitest";
import { enableAutoUnmount } from "@vue/test-utils";

enableAutoUnmount(afterEach);
window.scrollTo = () => undefined;

afterEach(() => {
  localStorage.clear();
  document.cookie = "bpn_locale=; Max-Age=0; Path=/";
});
