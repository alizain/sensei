import path from "node:path"
import { fileURLToPath } from "node:url"
import { reactRouter } from "@react-router/dev/vite"
import tailwindcss from "@tailwindcss/vite"
import { defineConfig } from "vite"
import svgr from "vite-plugin-svgr"
import tsconfigPaths from "vite-tsconfig-paths"

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
	plugins: [
		tailwindcss(),
		svgr({
			svgrOptions: {
				icon: true,
			},
		}),
		reactRouter(),
		tsconfigPaths(),
	],
	resolve: {
		alias: {
			// Alias for FontAwesome kit SVGs (the package doesn't export them directly)
			"@fa": path.resolve(
				__dirname,
				"../../node_modules/@awesome.me/kit-e146ba5a27/icons/svgs-full",
			),
		},
	},
})
