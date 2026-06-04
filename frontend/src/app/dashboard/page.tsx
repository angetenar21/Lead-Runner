"use client";

import { useState, useEffect } from "react";
import { useAuth, authFetch } from "@/lib/auth";
import ProtectedRoute from "@/components/ProtectedRoute";

const API_BASE = "http://localhost:8000";

interface Lead {
  id: string;
  name: string;
  role: string;
  company: string;
  industry: string;
  location: string;
  email: string;
  status: "idle" | "scraping" | "enriching" | "ready" | "failed";
  email_draft?: string;
  summary?: string;
}

function DashboardContent() {
  const { user, token, logout } = useAuth();
  const [leads, setLeads] = useState<Lead[]>([]);
  const [industry, setIndustry] = useState("");
  const [location, setLocation] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationStep, setGenerationStep] = useState<string>("");
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);
  const [errorMsg, setErrorMsg] = useState("");

  const fetchLeads = async () => {
    if (!token) return;
    try {
      const res = await authFetch(`${API_BASE}/api/leads`, token);
      if (res.ok) {
        const data = await res.json();
        setLeads(data);
        if (data.length > 0 && !selectedLead) {
          setSelectedLead(data[0]);
        }
      } else if (res.status === 401) {
        logout();
      } else {
        setErrorMsg("Failed to fetch leads from backend API");
      }
    } catch (err) {
      console.error(err);
      setErrorMsg("Could not connect to FastAPI server (port 8000)");
    }
  };

  useEffect(() => {
    fetchLeads();
  }, [token]);

  const handleClearLeads = async () => {
    if (!token) return;
    try {
      const res = await authFetch(`${API_BASE}/api/leads`, token, { method: "DELETE" });
      if (res.ok) {
        setLeads([]);
        setSelectedLead(null);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!industry || !token) return;

    setIsGenerating(true);
    setGenerationStep("Sending request to backend...");
    setErrorMsg("");

    try {
      const res = await authFetch(
        `${API_BASE}/api/generate?industry=${encodeURIComponent(industry)}&location=${encodeURIComponent(location)}`,
        token,
        { method: "POST" }
      );

      if (res.ok) {
        setGenerationStep("Scraping companies & enriching with Gemini AI...");

        const poll = setInterval(async () => {
          const leadsRes = await authFetch(`${API_BASE}/api/leads`, token!);
          if (leadsRes.ok) {
            const data = await leadsRes.json();
            const hasNewReady = data.some((l: Lead) => l.status === "ready" && !leads.find(ol => ol.id === l.id));
            if (hasNewReady || data.length > leads.length) {
              setLeads(data);
              if (data.length > 0) setSelectedLead(data[0]);
              clearInterval(poll);
              setIsGenerating(false);
              setGenerationStep("");
              setIndustry("");
              setLocation("");
            }
          }
        }, 2000);

        setTimeout(() => {
          clearInterval(poll);
          fetchLeads();
          setIsGenerating(false);
          setGenerationStep("");
        }, 60000);
      } else {
        setErrorMsg("Backend rejected request.");
        setIsGenerating(false);
        setGenerationStep("");
      }
    } catch (err) {
      setErrorMsg("Failed to connect to backend generator endpoint.");
      setIsGenerating(false);
      setGenerationStep("");
    }
  };

  // Get user initials for avatar
  const initials = user?.full_name
    ?.split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2) || "U";

  return (
    <div className="flex h-screen bg-slate-50 text-slate-900 font-sans overflow-hidden">

      {/* SIDEBAR */}
      <aside className="w-64 bg-white border-r border-slate-200 flex flex-col justify-between p-6">
        <div className="space-y-8">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-500 to-violet-600 flex items-center justify-center shadow-lg shadow-indigo-500/30">
              <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <div>
              <h1 className="font-bold text-lg leading-tight tracking-tight text-slate-900">LeadPulse</h1>
              <span className="text-xs text-indigo-600 font-semibold tracking-wider uppercase">AI Lead Gen</span>
            </div>
          </div>

          {/* Navigation */}
          <nav className="space-y-1">
            <a href="#" className="flex items-center gap-3 px-4 py-3 text-slate-900 bg-slate-100 rounded-xl font-medium transition-all">
              <svg className="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2H6a2 2 0 01-2-2v-4zM14 16a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2h-2a2 2 0 01-2-2v-4z" />
              </svg>
              Dashboard
            </a>
          </nav>
        </div>

        {/* User Card */}
        <div className="space-y-3">
          <div className="flex items-center gap-3 p-3 bg-slate-50 rounded-2xl border border-slate-200">
            <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-indigo-500 to-violet-600 flex items-center justify-center font-bold text-white text-sm">
              {initials}
            </div>
            <div className="flex-1 min-w-0">
              <h4 className="font-semibold text-sm leading-tight text-slate-900 truncate">{user?.full_name}</h4>
              <span className="text-xs text-slate-500 truncate block">{user?.email}</span>
            </div>
          </div>
          <button
            onClick={logout}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 text-xs text-slate-600 hover:text-red-600 hover:bg-red-50 rounded-xl border border-slate-200 transition-all"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            Sign Out
          </button>
        </div>
      </aside>

      {/* MAIN CONTAINER */}
      <main className="flex-1 flex flex-col overflow-hidden">

        {/* HEADER */}
        <header className="h-14 border-b border-slate-200 px-8 flex items-center bg-white/80 backdrop-blur-md">
          <div className="flex items-center gap-3">
            <span className="flex h-2.5 w-2.5 relative">
              <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${errorMsg ? "bg-red-400" : "bg-emerald-400"}`}></span>
              <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${errorMsg ? "bg-red-500" : "bg-emerald-500"}`}></span>
            </span>
            <span className="text-xs font-medium text-slate-500">
              {errorMsg ? errorMsg : "Backend API Connected (port 8000)"}
            </span>
          </div>
        </header>

        {/* SCROLLABLE MAIN CONTENT */}
        <div className="flex-1 overflow-y-auto p-8 space-y-8 bg-slate-50">

          {/* TITLE */}
          <div>
            <h2 className="text-2xl font-bold tracking-tight text-slate-900">Welcome back, {user?.full_name?.split(" ")[0]}</h2>
            <p className="text-slate-500 text-sm">Automate scraping and generate personalized outreach drafts in seconds.</p>
          </div>

          {/* STATS ROW */}
          <div className="grid grid-cols-3 gap-6">
            {[
              { label: "Total Leads", value: leads.length, sub: "In your account" },
              { label: "AI Enriched", value: leads.filter(l => l.status === "ready").length, sub: "Gemini processed" },
              { label: "Pipeline Status", value: isGenerating ? "Running" : "Idle", sub: isGenerating ? "Processing leads..." : "Ready to scan" },
            ].map((stat, idx) => (
              <div key={idx} className="bg-white p-5 rounded-2xl border border-slate-200 relative overflow-hidden group shadow-sm shadow-slate-200/50">
                <div className="absolute top-0 right-0 w-24 h-24 bg-gradient-to-br from-indigo-100 to-violet-100 opacity-50 blur-2xl group-hover:opacity-100 transition-all rounded-full" />
                <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{stat.label}</h4>
                <div className="mt-2">
                  <span className="text-3xl font-extrabold text-slate-900">{stat.value}</span>
                </div>
                <span className="mt-1 block text-xs font-medium text-slate-500">{stat.sub}</span>
              </div>
            ))}
          </div>

          {/* GENERATION BOX */}
          <section className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xl shadow-slate-200/50 relative overflow-hidden">
            <div className="absolute -right-16 -top-16 w-48 h-48 bg-indigo-100 rounded-full blur-3xl pointer-events-none" />
            <h3 className="text-lg font-bold mb-1 text-slate-900">Launch Lead Scanner</h3>
            <p className="text-slate-500 text-sm mb-6">Enter your target business profile to scrape contacts and draft customized emails.</p>

            <form onSubmit={handleGenerate} className="grid grid-cols-3 gap-6 items-end">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">Industry / Niche</label>
                <input
                  type="text"
                  value={industry}
                  onChange={e => setIndustry(e.target.value)}
                  placeholder="e.g. Software Agency, Dental Clinics"
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 text-sm transition-all"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">Location (Optional)</label>
                <input
                  type="text"
                  value={location}
                  onChange={e => setLocation(e.target.value)}
                  placeholder="e.g. New York, London"
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 text-sm transition-all"
                />
              </div>
              <div>
                <button
                  type="submit"
                  disabled={isGenerating || !industry}
                  className="w-full bg-gradient-to-r from-indigo-500 to-violet-600 hover:from-indigo-600 hover:to-violet-700 text-white rounded-xl px-6 py-3 font-semibold text-sm shadow-lg shadow-indigo-500/30 active:scale-[0.98] transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {isGenerating ? (
                    <>
                      <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      Running...
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                      </svg>
                      Generate Leads
                    </>
                  )}
                </button>
              </div>
            </form>

            {isGenerating && (
              <div className="mt-6 p-4 bg-indigo-50 rounded-xl border border-indigo-100 flex items-center gap-3">
                <span className="flex h-2.5 w-2.5 relative">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-indigo-500"></span>
                </span>
                <span className="text-xs font-medium text-indigo-700 animate-pulse">{generationStep}</span>
              </div>
            )}
          </section>

          {/* TABLE & OUTREACH VIEW SPLIT */}
          <div className="grid grid-cols-3 gap-8">
            {/* Leads Table */}
            <div className="col-span-2 bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm shadow-slate-200/50">
              <div className="p-6 border-b border-slate-200 flex items-center justify-between">
                <h3 className="text-lg font-bold text-slate-900">Scraped Contacts</h3>
                <div className="flex gap-2">
                  <button onClick={handleClearLeads} className="px-3 py-1.5 text-xs bg-red-50 hover:bg-red-100 text-red-600 border border-red-200 rounded-lg font-medium transition-all">
                    Clear Data
                  </button>
                  <button className="px-3 py-1.5 text-xs bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-700 rounded-lg font-medium transition-all">
                    Export to CSV
                  </button>
                </div>
              </div>

              <div className="overflow-x-auto min-h-[250px]">
                {leads.length > 0 ? (
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="border-b border-slate-200 bg-slate-50 text-slate-500 text-xs font-semibold uppercase tracking-wider">
                        <th className="px-6 py-4">Lead</th>
                        <th className="px-6 py-4">Company</th>
                        <th className="px-6 py-4">Location</th>
                        <th className="px-6 py-4">AI Status</th>
                        <th className="px-6 py-4 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 text-sm">
                      {leads.map(lead => (
                        <tr
                          key={lead.id}
                          onClick={() => setSelectedLead(lead)}
                          className={`hover:bg-slate-50 cursor-pointer transition-colors ${selectedLead?.id === lead.id ? "bg-slate-50" : ""}`}
                        >
                          <td className="px-6 py-4">
                            <div className="font-semibold text-slate-900">{lead.name}</div>
                            <div className="text-slate-500 text-xs">{lead.role}</div>
                          </td>
                          <td className="px-6 py-4">
                            <div className="font-medium text-slate-900">{lead.company}</div>
                            <div className="text-slate-500 text-xs">{lead.industry}</div>
                          </td>
                          <td className="px-6 py-4 text-slate-600">
                            {lead.location}
                          </td>
                          <td className="px-6 py-4">
                            <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                              lead.status === "ready"
                                ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                : "bg-amber-50 text-amber-700 border border-amber-200"
                            }`}>
                              <span className={`w-1.5 h-1.5 rounded-full ${lead.status === "ready" ? "bg-emerald-500" : "bg-amber-500"}`} />
                              {lead.status === "ready" ? "Enriched" : "Processing"}
                            </span>
                          </td>
                          <td className="px-6 py-4 text-right">
                            <button className="text-indigo-600 hover:text-indigo-700 font-semibold text-xs transition-all">
                              View Draft
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="flex flex-col items-center justify-center p-12 text-slate-500 text-center">
                    <svg className="w-12 h-12 mb-3 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                    </svg>
                    <h4 className="font-semibold text-slate-700">No leads in database</h4>
                    <p className="text-xs text-slate-500 mt-1">Type in a target industry above and hit &quot;Generate Leads&quot; to add data.</p>
                  </div>
                )}
              </div>
            </div>

            {/* AI Copy Preview */}
            <div className="bg-white rounded-2xl border border-slate-200 p-6 flex flex-col justify-between shadow-sm shadow-slate-200/50">
              {selectedLead ? (
                <div className="space-y-6 flex-1 flex flex-col">
                  <div>
                    <span className="text-xs font-semibold text-indigo-600 tracking-wider uppercase">AI Enrichment</span>
                    <h3 className="text-xl font-bold mt-1 leading-tight text-slate-900">{selectedLead.name}</h3>
                    <p className="text-slate-500 text-xs mt-1">{selectedLead.role} at <span className="text-slate-900 font-medium">{selectedLead.company}</span></p>
                  </div>

                  <div className="space-y-2">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Company Bio Summary</h4>
                    <div className="bg-slate-50 rounded-xl p-4 text-xs text-slate-700 leading-relaxed border border-slate-200">
                      {selectedLead.summary || "No summary available yet."}
                    </div>
                  </div>

                  <div className="space-y-2 flex-1 flex flex-col">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Outreach Email Draft</h4>
                    <textarea
                      value={selectedLead.email_draft || ""}
                      readOnly
                      className="w-full flex-1 bg-slate-50 rounded-xl p-4 text-xs text-slate-700 font-mono leading-relaxed border border-slate-200 resize-none focus:outline-none"
                    />
                  </div>

                  <div className="flex gap-3">
                    <a
                      href={`mailto:${selectedLead.email}?subject=Collaboration%20Proposal&body=${encodeURIComponent(selectedLead.email_draft || "")}`}
                      className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl py-2.5 font-semibold text-xs shadow-md shadow-indigo-600/20 text-center active:scale-[0.98] transition-all"
                    >
                      Send Email
                    </a>
                    <button
                      onClick={() => navigator.clipboard.writeText(selectedLead.email_draft || "")}
                      className="px-4 bg-white hover:bg-slate-50 text-slate-700 rounded-xl border border-slate-200 text-xs font-medium transition-all"
                    >
                      Copy
                    </button>
                  </div>
                </div>
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-center space-y-3">
                  <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center text-slate-400">
                    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                    </svg>
                  </div>
                  <div>
                    <h4 className="font-bold text-slate-900">No Lead Selected</h4>
                    <p className="text-xs text-slate-500 max-w-[200px] mt-1">Select a contact from the list to view their AI-enriched bio and customized email draft.</p>
                  </div>
                </div>
              )}
            </div>
          </div>

        </div>
      </main>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <ProtectedRoute>
      <DashboardContent />
    </ProtectedRoute>
  );
}
