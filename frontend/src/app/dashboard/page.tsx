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

interface Batch {
  id: number;
  industry: string;
  location: string;
  lead_count: number;
  status: string;
  created_at: string;
}

function DashboardContent() {
  const { user, token, logout } = useAuth();
  const [leads, setLeads] = useState<Lead[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [activeBatchId, setActiveBatchId] = useState<number | null>(null);
  const [industry, setIndustry] = useState("");
  const [location, setLocation] = useState("");
  const [autoEnrich, setAutoEnrich] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationStep, setGenerationStep] = useState<string>("");
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);
  const [errorMsg, setErrorMsg] = useState("");

  const fetchBatches = async () => {
    if (!token) return;
    try {
      const res = await authFetch(`${API_BASE}/api/batches`, token);
      if (res.ok) {
        const data = await res.json();
        setBatches(data);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const fetchLeads = async (batchId?: number | null) => {
    if (!token) return;
    try {
      const url = batchId
        ? `${API_BASE}/api/leads?batch_id=${batchId}`
        : `${API_BASE}/api/leads`;
      const res = await authFetch(url, token);
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
    fetchBatches();
  }, [token]);

  useEffect(() => {
    fetchLeads(activeBatchId);
    setSelectedLead(null);
  }, [activeBatchId, token]);

  const handleSelectBatch = (batchId: number) => {
    setActiveBatchId(batchId);
  };

  const handleDeleteBatch = async (batchId: number) => {
    if (!token) return;
    try {
      const res = await authFetch(`${API_BASE}/api/batches/${batchId}`, token, { method: "DELETE" });
      if (res.ok) {
        setBatches(prev => prev.filter(b => b.id !== batchId));
        if (activeBatchId === batchId) {
          setActiveBatchId(null);
          setLeads([]);
          setSelectedLead(null);
        }
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleClearLeads = async () => {
    if (!token) return;
    try {
      const res = await authFetch(`${API_BASE}/api/leads`, token, { method: "DELETE" });
      if (res.ok) {
        setLeads([]);
        setBatches([]);
        setSelectedLead(null);
        setActiveBatchId(null);
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
        `${API_BASE}/api/generate?industry=${encodeURIComponent(industry)}&location=${encodeURIComponent(location)}&auto_enrich=${autoEnrich}`,
        token,
        { method: "POST" }
      );

      if (res.ok) {
        const data = await res.json();
        const newBatchId = data.batch_id;
        setGenerationStep("Scraping companies...");

        // Set active batch to the new one
        setActiveBatchId(newBatchId);

        const poll = setInterval(async () => {
          // Poll leads for this specific batch
          const leadsRes = await authFetch(`${API_BASE}/api/leads?batch_id=${newBatchId}`, token!);
          if (leadsRes.ok) {
            const leadsData = await leadsRes.json();
            setLeads(leadsData);
            if (leadsData.length > 0 && !selectedLead) {
              setSelectedLead(leadsData[0]);
            }
          }

          // Also poll batch status
          const batchesRes = await authFetch(`${API_BASE}/api/batches`, token!);
          if (batchesRes.ok) {
            const batchesData = await batchesRes.json();
            setBatches(batchesData);
            const thisBatch = batchesData.find((b: Batch) => b.id === newBatchId);
            if (thisBatch && thisBatch.status === "completed") {
              clearInterval(poll);
              setIsGenerating(false);
              setGenerationStep("");
              setIndustry("");
              setLocation("");
              // Final fetch
              fetchLeads(newBatchId);
            }
          }
        }, 2500);

        setTimeout(() => {
          clearInterval(poll);
          fetchBatches();
          fetchLeads(newBatchId);
          setIsGenerating(false);
          setGenerationStep("");
        }, 90000);
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

  const handleEnrich = async (leadId: string) => {
    if (!token) return;

    setLeads(prev => prev.map(l => l.id === leadId ? { ...l, status: "enriching" } : l));
    if (selectedLead?.id === leadId) setSelectedLead({ ...selectedLead, status: "enriching" });

    try {
      const res = await authFetch(`${API_BASE}/api/leads/${leadId}/enrich`, token, { method: "POST" });
      if (res.ok) {
        const enrichedLead = await res.json();
        setLeads(prev => prev.map(l => l.id === leadId ? enrichedLead : l));
        if (selectedLead?.id === leadId) setSelectedLead(enrichedLead);
      } else {
        setLeads(prev => prev.map(l => l.id === leadId ? { ...l, status: "failed" } : l));
        if (selectedLead?.id === leadId) setSelectedLead({ ...selectedLead, status: "failed" });
      }
    } catch (err) {
      console.error(err);
      setLeads(prev => prev.map(l => l.id === leadId ? { ...l, status: "failed" } : l));
      if (selectedLead?.id === leadId) setSelectedLead({ ...selectedLead, status: "failed" });
    }
  };

  const initials = user?.full_name
    ?.split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2) || "U";

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  };

  return (
    <div className="flex h-screen bg-slate-50 text-slate-900 font-sans overflow-hidden">

      {/* SIDEBAR */}
      <aside className="w-72 bg-white border-r border-slate-200 flex flex-col justify-between">
        <div className="flex-1 overflow-hidden flex flex-col">
          {/* Logo */}
          <div className="p-6 pb-4">
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
          </div>

          {/* Search History */}
          <div className="px-6 pb-2">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">Search History</h3>
          </div>
          <div className="flex-1 overflow-y-auto px-3 space-y-1">
            {batches.length > 0 ? (
              batches.map(batch => (
                <div
                  key={batch.id}
                  onClick={() => handleSelectBatch(batch.id)}
                  className={`group flex items-center justify-between px-3 py-3 rounded-xl cursor-pointer transition-all ${
                    activeBatchId === batch.id
                      ? "bg-indigo-50 border border-indigo-200"
                      : "hover:bg-slate-50 border border-transparent"
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <div className={`font-medium text-sm truncate ${activeBatchId === batch.id ? "text-indigo-700" : "text-slate-900"}`}>
                      {batch.industry}
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-slate-400 truncate">{batch.location || "Anywhere"}</span>
                      <span className="text-slate-300">·</span>
                      <span className="text-xs text-slate-400">{batch.lead_count} leads</span>
                    </div>
                    <div className="text-xs text-slate-400 mt-0.5">{formatDate(batch.created_at)}</div>
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDeleteBatch(batch.id); }}
                    className="opacity-0 group-hover:opacity-100 ml-2 p-1 text-slate-400 hover:text-red-500 rounded transition-all"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              ))
            ) : (
              <div className="text-center py-8">
                <p className="text-xs text-slate-400">No searches yet</p>
                <p className="text-xs text-slate-400 mt-1">Generate your first batch above</p>
              </div>
            )}
          </div>
        </div>

        {/* User Card */}
        <div className="p-4 space-y-3 border-t border-slate-100">
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
              { label: "Total Leads", value: leads.length, sub: activeBatchId ? "In selected batch" : "In your account" },
              { label: "AI Enriched", value: leads.filter(l => l.status === "ready").length, sub: "Gemini / Groq processed" },
              { label: "Total Searches", value: batches.length, sub: "In search history" },
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
            <p className="text-slate-500 text-sm mb-6">Each scan creates a new entry in your search history on the left.</p>

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

            <div className="mt-5 flex items-center gap-3">
              <button
                type="button"
                onClick={() => setAutoEnrich(!autoEnrich)}
                className={`relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${autoEnrich ? "bg-indigo-600" : "bg-slate-200"}`}
              >
                <span className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${autoEnrich ? "translate-x-4" : "translate-x-0"}`} />
              </button>
              <span className="text-xs text-slate-500 font-medium">
                <strong className="text-slate-700">Auto-Enrich with AI</strong> (Automatically process all leads in background)
              </span>
            </div>

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
                <div>
                  <h3 className="text-lg font-bold text-slate-900">
                    {activeBatchId
                      ? `${batches.find(b => b.id === activeBatchId)?.industry || "Leads"}`
                      : "All Leads"
                    }
                  </h3>
                  {activeBatchId && (
                    <button onClick={() => setActiveBatchId(null)} className="text-xs text-indigo-600 hover:text-indigo-700 mt-0.5 font-medium">
                      ← Show all leads
                    </button>
                  )}
                </div>
                <div className="flex gap-2">
                  <button onClick={handleClearLeads} className="px-3 py-1.5 text-xs bg-red-50 hover:bg-red-100 text-red-600 border border-red-200 rounded-lg font-medium transition-all">
                    Clear All
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
                        <th className="px-6 py-4">Website</th>
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
                            {lead.status === "ready" ? (
                              <>
                                <div className="font-semibold text-slate-900">{lead.name}</div>
                                <div className="text-slate-500 text-xs">{lead.role}</div>
                              </>
                            ) : (
                              <>
                                <div className="font-medium text-slate-400 italic">Pending enrichment</div>
                                <div className="text-slate-400 text-xs">{lead.email}</div>
                              </>
                            )}
                          </td>
                          <td className="px-6 py-4">
                            <div className="font-medium text-slate-900">{lead.company}</div>
                            <div className="text-slate-500 text-xs">{lead.industry}</div>
                          </td>
                          <td className="px-6 py-4">
                            {lead.email && lead.email.includes("@") ? (
                              <a 
                                href={`https://${lead.email.split("@")[1]}`} 
                                target="_blank" 
                                rel="noopener noreferrer" 
                                className="text-indigo-600 hover:text-indigo-700 hover:underline font-medium"
                                onClick={e => e.stopPropagation()}
                              >
                                {lead.email.split("@")[1]}
                              </a>
                            ) : (
                              <span className="text-slate-400 italic">Unknown</span>
                            )}
                          </td>
                          <td className="px-6 py-4">
                            <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                              lead.status === "ready"
                                ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                : lead.status === "enriching"
                                ? "bg-blue-50 text-blue-700 border border-blue-200 animate-pulse"
                                : "bg-slate-100 text-slate-600 border border-slate-200"
                            }`}>
                              <span className={`w-1.5 h-1.5 rounded-full ${lead.status === "ready" ? "bg-emerald-500" : lead.status === "enriching" ? "bg-blue-500" : "bg-slate-400"}`} />
                              {lead.status === "ready" ? "Enriched" : lead.status === "enriching" ? "Enriching" : "Idle"}
                            </span>
                          </td>
                          <td className="px-6 py-4 text-right">
                            {lead.status === "ready" ? (
                              <button className="text-indigo-600 hover:text-indigo-700 font-semibold text-xs transition-all">
                                View Draft
                              </button>
                            ) : lead.status === "enriching" ? (
                              <span className="text-blue-500 text-xs font-medium">Working...</span>
                            ) : (
                              <button
                                onClick={(e) => { e.stopPropagation(); handleEnrich(lead.id); }}
                                className="text-indigo-600 hover:text-indigo-700 font-semibold text-xs transition-all"
                              >
                                Enrich
                              </button>
                            )}
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
                    <h4 className="font-semibold text-slate-700">No leads found</h4>
                    <p className="text-xs text-slate-500 mt-1">
                      {activeBatchId ? "This batch has no leads." : "Generate your first batch to see leads here."}
                    </p>
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
                    <h3 className="text-xl font-bold mt-1 leading-tight text-slate-900">
                      {selectedLead.status === "ready" ? selectedLead.name : selectedLead.company}
                    </h3>
                    <p className="text-slate-500 text-xs mt-1">
                      {selectedLead.status === "ready"
                        ? `${selectedLead.role} at ${selectedLead.company}`
                        : `${selectedLead.location} · ${selectedLead.email}`
                      }
                    </p>
                  </div>

                  <div className="space-y-2">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Company Bio Summary</h4>
                    <div className="bg-slate-50 rounded-xl p-4 text-xs text-slate-700 leading-relaxed border border-slate-200 max-h-32 overflow-y-auto">
                      {selectedLead.summary || "No summary available yet."}
                    </div>
                  </div>

                  <div className="space-y-2 flex-1 flex flex-col">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Outreach Email Draft</h4>
                    {selectedLead.status === "ready" ? (
                      <textarea
                        value={selectedLead.email_draft || ""}
                        readOnly
                        className="w-full flex-1 bg-slate-50 rounded-xl p-4 text-xs text-slate-700 font-mono leading-relaxed border border-slate-200 resize-none focus:outline-none"
                      />
                    ) : (
                      <div className="flex-1 bg-slate-50 rounded-xl p-4 border border-slate-200 flex flex-col items-center justify-center text-center space-y-4">
                        <div className="w-12 h-12 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-500">
                          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
                          </svg>
                        </div>
                        <div>
                          <h4 className="font-semibold text-slate-900">AI Enrichment Needed</h4>
                          <p className="text-xs text-slate-500 mt-1 max-w-[250px]">Extract deeper insights and draft a personalized cold email using Gemini AI.</p>
                        </div>
                        <button
                          onClick={() => handleEnrich(selectedLead.id)}
                          disabled={selectedLead.status === "enriching"}
                          className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs rounded-xl shadow-md shadow-indigo-600/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                        >
                          {selectedLead.status === "enriching" ? (
                            <>
                              <svg className="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                              </svg>
                              Enriching...
                            </>
                          ) : (
                            "Enrich Lead with AI"
                          )}
                        </button>
                      </div>
                    )}
                  </div>

                  <div className="flex gap-3">
                    <a
                      href={selectedLead.status === "ready" ? `mailto:${selectedLead.email}?subject=Collaboration%20Proposal&body=${encodeURIComponent(selectedLead.email_draft || "")}` : "#"}
                      className={`flex-1 rounded-xl py-2.5 font-semibold text-xs shadow-md text-center transition-all ${
                        selectedLead.status === "ready"
                          ? "bg-indigo-600 hover:bg-indigo-700 text-white shadow-indigo-600/20 active:scale-[0.98]"
                          : "bg-slate-100 text-slate-400 cursor-not-allowed"
                      }`}
                      onClick={(e) => {
                        if (selectedLead.status !== "ready") e.preventDefault();
                      }}
                    >
                      Send Email
                    </a>
                    <button
                      onClick={() => {
                        if (selectedLead.status === "ready") {
                          navigator.clipboard.writeText(selectedLead.email_draft || "");
                        }
                      }}
                      disabled={selectedLead.status !== "ready"}
                      className="px-4 bg-white hover:bg-slate-50 text-slate-700 rounded-xl border border-slate-200 text-xs font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed"
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
