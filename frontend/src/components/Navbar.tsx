// frontend/src/components/Navbar.tsx
import React from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { UserMenu } from "./UserMenu";
import SearchBar from "./SearchBar"; 

// NavLink component to handle active state and styling
function NavLink({ to, children }: { to: string; children: React.ReactNode }) {
  const loc = useLocation();
  const active = loc.pathname === to;
  return (
    <Link
      to={to}
      className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
        active ? "bg-gray-200 text-gray-900" : "text-gray-700 hover:bg-gray-100"
      }`}
    >
      {children}
    </Link>
  );
}

// Main Navbar component
export default function Navbar() {
  const { isAuthenticated } = useAuth();  // Check if the user is authenticated

  return (
    <header className="bg-white shadow-sm">
      <div className="container mx-auto px-4 py-3 flex items-center justify-between">
        {/* Left side - Logo and Navigation */}
        <div className="flex items-center gap-4">
          <div className="text-lg font-semibold text-gray-900">Music Manager</div>
          <nav className="flex gap-3 items-center">
            <NavLink to="/">Home</NavLink>
            <NavLink to="/library">Library</NavLink>
            <NavLink to="/browse">Browse</NavLink>
            <NavLink to="/settings">Settings</NavLink>
          </nav>
        </div>

        {/* Right side - Search Bar and User Menu */}
        <div className="flex items-center gap-4">
          {/* Optionally, include a search bar */}
          <SearchBar />
          
          {/* Conditionally render UserMenu if authenticated */}
          {isAuthenticated && <UserMenu />}
        </div>
      </div>
    </header>
  );
}