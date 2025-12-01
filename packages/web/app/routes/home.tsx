import { Header } from "../components/Header"
import type { Route } from "./+types/home"

export function meta(_args: Route.MetaArgs) {
	return [
		{ title: "Sensei - Intelligent Documentation for AI Coding Assistants" },
		{
			content:
				"Sensei solves the context pollution problem by being a specialized agent that orchestrates multiple knowledge sources and returns curated, accurate documentation with code examples.",
			name: "description",
		},
	]
}

export default function Home() {
	return (
		<>
			<Header />

			<main className="flex-1">
				<div className="w-full mx-auto max-w-4xl px-6 py-12 space-y-8">
					<div className="space-y-4">
						<h1 className="text-3xl font-semibold leading-tight">
							Intelligent documentation for AI coding assistants.
						</h1>
						<p className="text-lg text-slate-600">
							Sensei solves the context pollution problem by orchestrating
							multiple knowledge sources and returning curated, accurate
							documentation with code examples.
						</p>
					</div>

					<div className="flex gap-4">
						<a
							href="https://github.com/yourusername/sensei"
							target="_blank"
							rel="noopener noreferrer"
							className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-slate-900 rounded-md hover:bg-slate-800"
						>
							Get Started &rarr;
						</a>
					</div>
				</div>

				<div className="w-full mx-auto max-w-4xl px-6 py-8 space-y-6">
					<h2 className="text-xl font-semibold text-slate-900">Features</h2>

					<div className="grid gap-6 md:grid-cols-2">
						<div className="space-y-2">
							<h3 className="font-medium text-slate-900">
								Multi-Source Documentation
							</h3>
							<p className="text-sm text-slate-600">
								Searches Context7, Tavily, and more to find the most
								relevant documentation for your query.
							</p>
						</div>

						<div className="space-y-2">
							<h3 className="font-medium text-slate-900">
								Intelligent Synthesis
							</h3>
							<p className="text-sm text-slate-600">
								Uses Claude to synthesize information from multiple
								sources into coherent, actionable answers.
							</p>
						</div>

						<div className="space-y-2">
							<h3 className="font-medium text-slate-900">MCP Server</h3>
							<p className="text-sm text-slate-600">
								Expose Sensei as an MCP tool for AI coding agents like
								Claude Code, Cursor, and Windsurf.
							</p>
						</div>

						<div className="space-y-2">
							<h3 className="font-medium text-slate-900">Self-Hostable</h3>
							<p className="text-sm text-slate-600">
								Run locally with SQLite or deploy with PostgreSQL. Your
								data, your infrastructure.
							</p>
						</div>
					</div>
				</div>

				<div className="w-full mx-auto max-w-4xl px-6 py-8">
					<div className="border border-slate-200 rounded-lg p-6 bg-slate-50">
						<h2 className="text-lg font-semibold text-slate-900 mb-2">
							Quick Start
						</h2>
						<pre className="text-sm text-slate-700 overflow-x-auto">
							<code>{`# Clone and install
git clone https://github.com/yourusername/sensei.git
cd sensei && uv sync

# Run Sensei
uv run sensei`}</code>
						</pre>
					</div>
				</div>
			</main>

			<footer className="w-full mx-auto max-w-4xl px-6 py-8 border-t border-slate-100">
				<p className="text-sm text-slate-500">
					MIT License &middot;{" "}
					<a
						href="https://github.com/yourusername/sensei"
						target="_blank"
						rel="noopener noreferrer"
						className="hover:text-slate-700"
					>
						GitHub
					</a>
				</p>
			</footer>
		</>
	)
}
