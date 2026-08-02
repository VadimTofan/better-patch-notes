import "@fontsource/manrope/400.css";
import "@fontsource/manrope/600.css";
import "@fontsource/sora/600.css";
import "@fontsource/sora/700.css";
import "@/styles/global.scss";

import { createApp } from "vue";

import App from "./App.vue";
import { router } from "./router";

createApp(App).use(router).mount("#app");
