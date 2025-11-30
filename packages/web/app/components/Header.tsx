import FaGithub from "@fa/brands/github.svg?react"
import { Link } from "react-router"
import { FontAwesomeIcon } from "~/lib/fontawesome"

export interface NavItem {
	label: string
	href: string
}

export interface HeaderProps {
	navItems?: NavItem[]
}

export function Header({ navItems = [] }: HeaderProps) {
	return (
		<header>
			<nav
				aria-label="Global"
				className="mx-auto flex max-w-4xl items-center justify-between py-4 px-6"
			>
				<Link
					to="/"
					className="-m-1.5 px-1.5 py-2"
				>
					<span className="sr-only">Sensei</span>
					<span className="text-xl font-medium tracking-tight">sensei</span>
				</Link>
				<div className="flex gap-x-6 items-center">
					{navItems.map((item) => (
						<Link
							key={item.href}
							to={item.href}
							className="text-sm text-slate-600 hover:text-slate-900"
						>
							{item.label}
						</Link>
					))}
					<a
						href="https://github.com/yourusername/sensei"
						target="_blank"
						rel="noopener noreferrer"
						className="flex items-center gap-2 text-sm font-medium text-slate-900 hover:text-slate-600"
					>
						<FontAwesomeIcon
							icon={FaGithub}
							alt="GitHub"
							className="size-5"
						/>
						<span>GitHub</span>
					</a>
				</div>
			</nav>
		</header>
	)
}
