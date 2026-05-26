import { useState, useEffect, useRef, useCallback } from "react";
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import {
  ConfigProvider,
  Select,
  Table,
  Drawer,
  theme as antTheme,
  message as antMessage,
} from "antd";
import {
  Sparkles,
  BarChart3,
  Database,
  MessageSquare,
  Send,
  Plus,
  Trash2,
  Activity,
  Clock,
  Coins,
  AlertTriangle,
  Cpu,
  Layers,
  ShieldCheck,
  Ban,
  Terminal,
  ChevronRight,
  Zap,
} from "lucide-react";
import { apiService, type MessageResponse, type TelemetryLogResponse } from "./api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import * as echarts from "echarts";

// ─── Query client ───────────────────────────────────────────
const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } },
});

// ─── Ant Design minimal dark theme override ─────────────────
const antConfig = {
  algorithm: antTheme.darkAlgorithm,
  token: {
    colorPrimary: "#fafafa",
    colorBgBase: "#09090b",
    colorBgContainer: "#18181b",
    colorBorder: "rgba(255,255,255,0.07)",
    colorText: "#fafafa",
    colorTextSecondary: "#a1a1aa",
    fontFamily: "Inter",
    borderRadius: 8,
  },
  components: {
    Table: {
      headerBg: "#1f1f23",
      rowHoverBg: "rgba(255,255,255,0.02)",
      borderColor: "rgba(255,255,255,0.06)",
    },
    Drawer: {
      colorBgElevated: "#09090b",
    },
  },
};

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ConfigProvider theme={antConfig}>
        <DashboardApp />
      </ConfigProvider>
    </QueryClientProvider>
  );
}

// ─── Auto-resize textarea helper ────────────────────────────
function useAutoResize(ref: React.RefObject<HTMLTextAreaElement | null>, value: string) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 140) + "px";
  }, [value]);
}

// ─── Apache ECharts Component ──────────────────────────────
function EChartComponent({ data, dataKey }: { data: any[]; dataKey: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = echarts.init(containerRef.current);
    chartRef.current = chart;

    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.dispose();
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !data || data.length === 0) return;

    const values = data.map((d) => d[dataKey] as number);
    const times = data.map((d) => {
      if (d.timestamp) {
        return new Date(d.timestamp).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        });
      }
      return "";
    });

    const isLatency = dataKey === "latency_ms";
    const unit = isLatency ? "ms" : "t/s";

    const option: echarts.EChartsOption = {
      backgroundColor: "transparent",
      grid: {
        top: 15,
        bottom: 20,
        left: 45,
        right: 15,
        containLabel: false,
      },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(0, 0, 0, 0.95)",
        borderColor: "rgba(255, 255, 255, 0.15)",
        textStyle: {
          color: "#ffffff",
          fontFamily: "Inter",
          fontSize: 11,
        },
        borderWidth: 1,
        borderRadius: 6,
        padding: [6, 10],
        formatter: (params: any) => {
          const item = params[0];
          return `<div style="font-family: Inter, sans-serif;">
            <div style="color: rgba(255, 255, 255, 0.5); font-size: 10px; margin-bottom: 2px;">${item.name}</div>
            <div style="display: flex; items-center; gap: 6px;">
              <span style="font-weight: 700; color: #ffffff;">${item.value} ${unit}</span>
            </div>
          </div>`;
        },
      },
      xAxis: {
        type: "category",
        data: times,
        boundaryGap: false,
        axisLine: {
          lineStyle: {
            color: "rgba(255, 255, 255, 0.08)",
          },
        },
        axisTick: { show: false },
        axisLabel: {
          color: "rgba(255, 255, 255, 0.35)",
          fontFamily: "JetBrains Mono",
          fontSize: 9,
        },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: "rgba(255, 255, 255, 0.35)",
          fontFamily: "JetBrains Mono",
          fontSize: 9,
        },
        splitLine: {
          lineStyle: {
            color: "rgba(255, 255, 255, 0.04)",
            type: "dashed",
          },
        },
      },
      series: [
        {
          data: values,
          type: "line",
          smooth: true,
          showSymbol: false,
          lineStyle: {
            color: "#ffffff",
            width: 1.5,
          },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "rgba(255, 255, 255, 0.08)" },
              { offset: 1, color: "rgba(255, 255, 255, 0)" },
            ]),
          },
        },
      ],
    };

    chart.setOption(option);
  }, [data, dataKey]);

  return <div ref={containerRef} style={{ width: "100%", height: "100%" }} />;
}

// ─── Main app ────────────────────────────────────────────────
function DashboardApp() {
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState<"chat" | "dashboard">("chat");
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [chatInput, setChatInput] = useState("");
  const [provider, setProvider] = useState<"mock" | "gemini" | "openai">("mock");
  const [model, setModel] = useState<string>("mock-llm");
  const [isGenerating, setIsGenerating] = useState(false);
  const [streamMessages, setStreamMessages] = useState<MessageResponse[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [inspectLog, setInspectLog] = useState<TelemetryLogResponse | null>(null);
  const [flashingLogs, setFlashingLogs] = useState<Record<string, "success" | "error">>({});

  useAutoResize(textareaRef, chatInput);

  // ── Queries ───────────────────────────────────────────────
  const conversationsQuery = useQuery({ queryKey: ["conversations"], queryFn: apiService.getConversations });
  const messagesQuery     = useQuery({ queryKey: ["messages", activeConversationId], queryFn: () => apiService.getMessages(activeConversationId!), enabled: !!activeConversationId });
  const metricsQuery      = useQuery({ queryKey: ["metrics"],    queryFn: apiService.getMetrics });
  const timeseriesQuery   = useQuery({ queryKey: ["timeseries"], queryFn: apiService.getTimeseries });
  const logsQuery         = useQuery({ queryKey: ["logs"],       queryFn: apiService.getRecentLogs });

  // ── Mutations ─────────────────────────────────────────────
  const createConvMutation = useMutation({
    mutationFn: apiService.createConversation,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["conversations"] });
      setActiveConversationId(data.id);
      setActiveTab("chat");
      setStreamMessages([]);
      antMessage.success("New conversation started.");
    },
    onError: () => antMessage.error("Failed to create conversation."),
  });

  const deleteConvMutation = useMutation({
    mutationFn: apiService.deleteConversation,
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ["conversations"] });
      if (activeConversationId === id) { setActiveConversationId(null); setStreamMessages([]); }
      antMessage.info("Conversation cleared.");
    },
    onError: () => antMessage.error("Failed to remove conversation."),
  });

  // ── Effects ───────────────────────────────────────────────
  useEffect(() => {
    if (conversationsQuery.data?.length && !activeConversationId) {
      setActiveConversationId(conversationsQuery.data[0].id);
    }
  }, [conversationsQuery.data]);

  useEffect(() => {
    if (messagesQuery.data) setStreamMessages(messagesQuery.data);
  }, [messagesQuery.data]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [streamMessages, isGenerating]);

  // ── WebSocket telemetry ───────────────────────────────────
  useEffect(() => {
    const ws = new WebSocket("ws://localhost:8005/api/ws/analytics");
    ws.onmessage = (e) => {
      try {
        const log: TelemetryLogResponse = JSON.parse(e.data);
        qc.setQueryData<TelemetryLogResponse[]>(["logs"], (prev) => prev ? [log, ...prev.slice(0, 49)] : [log]);
        setFlashingLogs((p) => ({ ...p, [log.id]: log.status as "success" | "error" }));
        setTimeout(() => setFlashingLogs((p) => { const n = { ...p }; delete n[log.id]; return n; }), 900);
        qc.invalidateQueries({ queryKey: ["metrics"] });
        qc.invalidateQueries({ queryKey: ["timeseries"] });
      } catch {}
    };
    return () => ws.close();
  }, [qc]);

  // ── Submit prompt ─────────────────────────────────────────
  const submitPrompt = useCallback(async () => {
    if (!chatInput.trim() || !activeConversationId || isGenerating) return;
    const prompt = chatInput;
    setChatInput("");
    setIsGenerating(true);

    const userMsg: MessageResponse = { id: crypto.randomUUID(), role: "user", content: prompt, created_at: new Date().toISOString() };
    const assistantId = crypto.randomUUID();
    const assistantMsg: MessageResponse = { id: assistantId, role: "assistant", content: "", created_at: new Date().toISOString() };
    setStreamMessages((p) => [...p, userMsg, assistantMsg]);

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      const res = await fetch(`http://localhost:8005/api/conversations/${activeConversationId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, provider, model }),
        signal: ctrl.signal,
      });
      if (!res.body) throw new Error("No stream");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let text = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        for (const seg of decoder.decode(value).split("\n")) {
          if (seg.startsWith("data: ")) {
            try {
              const d = JSON.parse(seg.slice(6));
              if (d.content) {
                text += d.content;
                setStreamMessages((p) => p.map((m) => m.id === assistantId ? { ...m, content: text } : m));
              }
            } catch {}
          }
        }
      }
    } catch (err: any) {
      const suffix = err.name === "AbortError" ? " [Cancelled]" : " [Stream error]";
      setStreamMessages((p) => p.map((m) => m.id === assistantId ? { ...m, content: m.content + suffix } : m));
    } finally {
      setIsGenerating(false);
      abortRef.current = null;
      qc.invalidateQueries({ queryKey: ["conversations"] });
    }
  }, [chatInput, activeConversationId, isGenerating, provider, model]);

  const cancelGeneration = () => { abortRef.current?.abort(); setIsGenerating(false); };

  const handleProviderChange = (val: string) => {
    const p = val as "mock" | "gemini" | "openai";
    setProvider(p);
    if (p === "mock")   setModel("mock-llm");
    if (p === "gemini") setModel("gemini-1.5-flash");
    if (p === "openai") setModel("gpt-4o");
  };


  // ── Telemetry table columns ───────────────────────────────
  const telemetryColumns = [
    {
      title: "Status", dataIndex: "status", key: "status",
      render: (s: string) => (
        <span className={`badge ${s === "success" ? "badge-success" : "badge-error"}`}>{s}</span>
      ),
    },
    {
      title: "Provider / Model", key: "model",
      render: (_: any, r: TelemetryLogResponse) => (
        <span style={{ fontSize: 12 }}>
          <span style={{ color: "var(--text)", fontWeight: 600 }}>{r.provider}</span>
          <span style={{ color: "var(--text-subtle)", margin: "0 5px" }}>/</span>
          <span style={{ color: "var(--text-muted)" }}>{r.model}</span>
        </span>
      ),
    },
    {
      title: "Latency", dataIndex: "latency_ms", key: "latency_ms",
      sorter: (a: TelemetryLogResponse, b: TelemetryLogResponse) => a.latency_ms - b.latency_ms,
      render: (l: number) => <span style={{ fontFamily: "JetBrains Mono", fontSize: 11.5, color: "var(--text-muted)" }}>{l}ms</span>,
    },
    {
      title: "Tokens (I/O)", key: "tokens",
      render: (_: any, r: TelemetryLogResponse) => (
        <span style={{ fontFamily: "JetBrains Mono", fontSize: 11, color: "var(--text-muted)" }}>
          {r.tokens_total}
          <span style={{ color: "var(--text-subtle)", marginLeft: 5 }}>
            ({r.tokens_prompt}/{r.tokens_completion})
          </span>
        </span>
      ),
    },
    {
      title: "PII", dataIndex: "pii_redacted", key: "pii",
      render: (v: boolean) => v
        ? <span className="badge badge-warning"><ShieldCheck size={9} /> Redacted</span>
        : <span style={{ color: "var(--text-subtle)", fontSize: 11 }}>—</span>,
    },
    {
      title: "Time", dataIndex: "timestamp", key: "ts",
      render: (t: string) => (
        <span style={{ fontSize: 11, color: "var(--text-subtle)", fontFamily: "JetBrains Mono" }}>
          {new Date(t).toLocaleTimeString()}
        </span>
      ),
    },
  ];

  // ── Render ────────────────────────────────────────────────
  return (
    <div className="main-layout">

      {/* ── Shadcn-style Sidebar ─────────────────────────────── */}
      <aside className="sidebar animate-slide-in">
        {/* Logo header */}
        <div className="sidebar-header">
          <div className="sidebar-logo">
            <Sparkles size={15} />
          </div>
          <span className="sidebar-brand">Ollive Trace</span>
        </div>

        <div style={{ padding: "10px 8px 0" }}>
          {/* New conversation */}
          <button className="new-conv-btn" onClick={() => createConvMutation.mutate(undefined)}>
            <Plus size={14} />
            {createConvMutation.isPending ? "Creating…" : "New Conversation"}
          </button>

          {/* Nav items */}
          <div
            className={`sidebar-item ${activeTab === "chat" ? "active" : ""}`}
            onClick={() => setActiveTab("chat")}
          >
            <MessageSquare size={14} className="item-icon" />
            Chatbot View
            {activeTab === "chat" && <ChevronRight size={12} style={{ marginLeft: "auto", opacity: 0.4 }} />}
          </div>
          <div
            className={`sidebar-item ${activeTab === "dashboard" ? "active" : ""}`}
            onClick={() => {
              setActiveTab("dashboard");
              qc.invalidateQueries({ queryKey: ["metrics"] });
              qc.invalidateQueries({ queryKey: ["timeseries"] });
            }}
          >
            <BarChart3 size={14} className="item-icon" />
            Telemetry Analytics
            {activeTab === "dashboard" && <ChevronRight size={12} style={{ marginLeft: "auto", opacity: 0.4 }} />}
          </div>
        </div>

        {/* Conversations list */}
        {activeTab === "chat" && (
          <>
            <div className="sidebar-section-label">Conversations</div>
            <div className="sidebar-body">
              {conversationsQuery.isLoading ? (
                <div style={{ padding: "12px 10px", color: "var(--text-subtle)", fontSize: 11.5, fontWeight: 500 }}>
                  Loading…
                </div>
              ) : (conversationsQuery.data || []).map((conv, idx) => (
                <div
                  key={conv.id}
                  className={`sidebar-item animate-fade-in ${activeConversationId === conv.id ? "active" : ""}`}
                  style={{ animationDelay: `${idx * 30}ms` }}
                  onClick={() => { setActiveConversationId(conv.id); setStreamMessages([]); }}
                >
                  <MessageSquare size={13} className="item-icon" />
                  <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 12.5 }}>
                    {conv.title}
                  </span>
                  <button
                    className="item-trash"
                    onClick={(e) => { e.stopPropagation(); deleteConvMutation.mutate(conv.id); }}
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}
            </div>
          </>
        )}

        {/* Footer status */}
        <div className="sidebar-footer">
          <div style={{ display: "flex", alignItems: "center", gap: 7, padding: "0 4px", fontSize: 11, color: "var(--text-subtle)" }}>
            <Database size={11} />
            <span>PostgreSQL Pipeline</span>
            <span className="live-dot" style={{ marginLeft: "auto" }} />
          </div>
        </div>
      </aside>

      {/* ── Main content ─────────────────────────────────────── */}
      <div className="main-content">

        {/* Top bar */}
        <header className="topbar">
          <div className="tab-group">
            <button
              className={`tab-btn ${activeTab === "chat" ? "active" : ""}`}
              onClick={() => setActiveTab("chat")}
            >
              <MessageSquare size={13} />
              Chatbot
            </button>
            <button
              className={`tab-btn ${activeTab === "dashboard" ? "active" : ""}`}
              onClick={() => { setActiveTab("dashboard"); qc.invalidateQueries({ queryKey: ["metrics"] }); }}
            >
              <BarChart3 size={13} />
              Analytics
            </button>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {isGenerating && (
              <div className="animate-scale-in" style={{
                display: "flex", alignItems: "center", gap: 7,
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: 20, padding: "4px 12px",
                fontSize: 11.5, fontWeight: 600, color: "var(--text-muted)",
              }}>
                <span className="live-dot" style={{ background: "var(--text-muted)" }} />
                Streaming…
              </div>
            )}
          </div>
        </header>

        {/* ── Chat view ─────────────────────────────────────── */}
        {activeTab === "chat" ? (
          <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

            {/* Model selector bar */}
            <div style={{
              padding: "10px 24px",
              borderBottom: "1px solid var(--border)",
              display: "flex", alignItems: "center", gap: 16, flexShrink: 0,
              background: "rgba(0, 0, 0, 0.4)", backdropFilter: "blur(12px)",
            }}>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-subtle)", marginBottom: 5 }}>
                  Provider
                </div>
                <Select
                  value={provider}
                  onChange={handleProviderChange}
                  className="custom-select"
                  style={{ width: 175 }}
                  popupClassName="select-dropdown"
                  size="small"
                >
                  <Select.Option value="mock">Mock Engine</Select.Option>
                  <Select.Option value="gemini">Gemini API</Select.Option>
                  <Select.Option value="openai">OpenAI API</Select.Option>
                </Select>
              </div>

              <div>
                <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-subtle)", marginBottom: 5 }}>
                  Model
                </div>
                {provider === "mock" && (
                  <Select value={model} style={{ width: 185 }} disabled size="small">
                    <Select.Option value="mock-llm">Mock Telemetry LLM</Select.Option>
                  </Select>
                )}
                {provider === "gemini" && (
                  <Select value={model} onChange={setModel} className="custom-select" style={{ width: 185 }} popupClassName="select-dropdown" size="small">
                    <Select.Option value="gemini-1.5-flash">Gemini 1.5 Flash</Select.Option>
                    <Select.Option value="gemini-1.5-pro">Gemini 1.5 Pro</Select.Option>
                  </Select>
                )}
                {provider === "openai" && (
                  <Select value={model} onChange={setModel} className="custom-select" style={{ width: 185 }} popupClassName="select-dropdown" size="small">
                    <Select.Option value="gpt-4o">GPT-4o</Select.Option>
                    <Select.Option value="gpt-4o-mini">GPT-4o Mini</Select.Option>
                    <Select.Option value="o1-mini">o1-mini</Select.Option>
                  </Select>
                )}
              </div>

              <div style={{ marginLeft: "auto" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11.5, color: "var(--text-subtle)", fontWeight: 500 }}>
                  <Zap size={12} />
                  SSE Streaming
                </div>
              </div>
            </div>

            {/* Chat feed */}
            {activeConversationId ? (
              <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
                <div style={{ flex: 1, overflowY: "auto", padding: "28px 32px", display: "flex", flexDirection: "column", gap: 20 }}>

                  {streamMessages.length === 0 ? (
                    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", textAlign: "center" }}>
                      <div style={{
                        width: 56, height: 56, borderRadius: 16,
                        background: "var(--bg-panel)", border: "1px solid var(--border)",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        marginBottom: 16, color: "var(--text-muted)",
                      }}>
                        <Sparkles size={22} />
                      </div>
                      <h3 style={{ fontSize: 15, fontWeight: 700, color: "var(--text)", margin: "0 0 8px" }}>
                        Start a conversation
                      </h3>
                      <p style={{ fontSize: 12.5, color: "var(--text-subtle)", lineHeight: 1.7, maxWidth: 320, margin: 0 }}>
                        Send a message to begin. Telemetry is recorded in real-time with PII redaction.
                      </p>
                    </div>
                  ) : (
                    streamMessages.map((msg, idx) => (
                      <div
                        key={msg.id}
                        className="animate-fade-in"
                        style={{
                          display: "flex",
                          gap: 12,
                          flexDirection: msg.role === "user" ? "row-reverse" : "row",
                          alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
                          maxWidth: "78%",
                          animationDelay: `${Math.min(idx * 20, 120)}ms`,
                        }}
                      >
                        {/* Avatar */}
                        <div className="avatar">
                          {msg.role === "user" ? <Cpu size={13} /> : <Sparkles size={13} />}
                        </div>

                        {/* Bubble */}
                        {msg.role === "user" ? (
                          <div className="chat-bubble-user">{msg.content}</div>
                        ) : (
                          <div className="chat-bubble-bot">
                            {msg.content === "" && isGenerating ? (
                              <div style={{ display: "flex", gap: 4, alignItems: "center", padding: "4px 0" }}>
                                <span className="typing-dot" />
                                <span className="typing-dot" />
                                <span className="typing-dot" />
                              </div>
                            ) : (
                              <div className="md-body">
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                  {msg.content}
                                </ReactMarkdown>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    ))
                  )}
                  <div ref={chatEndRef} />
                </div>

                {/* Input area */}
                <div style={{ padding: "16px 24px", borderTop: "1px solid var(--border)", flexShrink: 0, background: "rgba(0, 0, 0, 0.55)", backdropFilter: "blur(16px)" }}>
                  <div style={{ maxWidth: 860, margin: "0 auto" }}>
                    <div className="chat-input-wrap">
                      <textarea
                        ref={textareaRef}
                        className="chat-textarea"
                        value={chatInput}
                        rows={1}
                        placeholder="Ask anything… (try 'my email is test@test.com' to test PII redaction)"
                        onChange={(e) => setChatInput(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submitPrompt(); } }}
                      />
                      {isGenerating ? (
                        <button className="btn btn-danger btn-icon" onClick={cancelGeneration} title="Cancel">
                          <Ban size={14} />
                        </button>
                      ) : (
                        <button className="btn btn-primary btn-icon" onClick={submitPrompt} title="Send">
                          <Send size={14} />
                        </button>
                      )}
                    </div>
                    <div style={{ marginTop: 8, fontSize: 10.5, color: "var(--text-subtle)", textAlign: "center" }}>
                      Press <kbd style={{ background: "var(--bg-raised)", border: "1px solid var(--border)", borderRadius: 3, padding: "1px 5px", fontSize: 10, fontFamily: "JetBrains Mono" }}>Enter</kbd> to send · <kbd style={{ background: "var(--bg-raised)", border: "1px solid var(--border)", borderRadius: 3, padding: "1px 5px", fontSize: 10, fontFamily: "JetBrains Mono" }}>Shift+Enter</kbd> for new line
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", color: "var(--text-subtle)" }}>
                <MessageSquare size={28} style={{ marginBottom: 10, opacity: 0.25 }} />
                <span style={{ fontSize: 12.5, fontWeight: 600 }}>Select or create a conversation</span>
              </div>
            )}
          </div>

        ) : (
          /* ── Dashboard / Analytics view ─────────────────── */
          <div style={{ flex: 1, overflowY: "auto", padding: "28px 28px", display: "flex", flexDirection: "column", gap: 20 }}>

            {/* Metric cards */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}>
              {[
                { icon: <Clock size={17} />, label: "Avg Latency",       value: `${metricsQuery.data?.avg_latency_ms || 0}ms` },
                { icon: <Activity size={17} />, label: "Throughput",     value: `${metricsQuery.data?.avg_throughput_tps || 0} t/s` },
                { icon: <Coins size={17} />, label: "Total Tokens",       value: (metricsQuery.data?.total_tokens || 0).toLocaleString() },
                { icon: <AlertTriangle size={17} />, label: "Error Rate", value: `${metricsQuery.data?.error_rate || 0}%` },
              ].map((card, i) => (
                <div key={i} className="metric-card animate-fade-in" style={{ animationDelay: `${i * 50}ms` }}>
                  <div className="metric-icon">{card.icon}</div>
                  <div>
                    <div className="metric-label">{card.label}</div>
                    <div className="metric-value">{card.value}</div>
                  </div>
                </div>
              ))}
            </div>

            {/* Charts */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
              {[
                { title: "Latency Trends", sub: "Real-time · ms", key: "latency_ms",    color: "rgba(255,255,255,0.7)" },
                { title: "Token Throughput", sub: "Real-time · t/s", key: "throughput_tps", color: "rgba(255,255,255,0.45)" },
              ].map((chart, i) => (
                <div key={i} className="panel animate-fade-in" style={{ padding: 20, animationDelay: `${200 + i * 60}ms` }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                    <div>
                      <div style={{ fontSize: 12.5, fontWeight: 700, color: "var(--text)" }}>{chart.title}</div>
                      <div style={{ fontSize: 10.5, color: "var(--text-subtle)", marginTop: 2 }}>{chart.sub}</div>
                    </div>
                    <span className="badge badge-neutral" style={{ gap: 5 }}>
                      <span className="live-dot" style={{ width: 5, height: 5 }} />
                      Live
                    </span>
                  </div>
                  <div style={{ height: 130 }}>
                    {!timeseriesQuery.data || timeseriesQuery.data.length < 2 ? (
                      <div className="flex flex-col items-center justify-center h-full" style={{ color: "var(--text-subtle)" }}>
                        <Activity size={18} className="mb-2 opacity-40 animate-pulse" />
                        <span style={{ fontSize: 9.5, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em" }}>
                          Awaiting data
                        </span>
                      </div>
                    ) : (
                      <EChartComponent data={timeseriesQuery.data} dataKey={chart.key} />
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Telemetry table */}
            <div className="panel animate-fade-in" style={{ padding: 20, animationDelay: "360ms" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                  <Layers size={15} style={{ color: "var(--text-muted)" }} />
                  <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text)" }}>Live Telemetry Feed</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 11.5, color: "var(--text-subtle)", fontWeight: 500 }}>
                  <span className="live-dot" />
                  WebSocket Active
                </div>
              </div>

              <Table
                dataSource={logsQuery.data || []}
                columns={telemetryColumns}
                rowKey="id"
                loading={logsQuery.isLoading}
                pagination={{ pageSize: 7, size: "small" }}
                onRow={(record) => ({
                  onClick: () => setInspectLog(record),
                  className: flashingLogs[record.id]
                    ? `telemetry-row-${flashingLogs[record.id]} cursor-pointer`
                    : "cursor-pointer",
                })}
                className="custom-ant-table"
                size="small"
              />
            </div>
          </div>
        )}
      </div>

      {/* ── Telemetry Inspector Drawer ─────────────────────── */}
      <Drawer
        title={
          <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
            <Terminal size={14} style={{ color: "var(--text-muted)" }} />
            <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text)" }}>Telemetry Inspector</span>
          </div>
        }
        placement="right"
        onClose={() => setInspectLog(null)}
        open={!!inspectLog}
        width={560}
        className="custom-drawer"
        styles={{
          header: { background: "var(--bg-panel)", borderBottom: "1px solid var(--border)", padding: "14px 20px" },
          body:   { background: "var(--bg)", padding: 20 },
          mask:   { backdropFilter: "blur(3px)" },
        }}
      >
        {inspectLog && (
          <div style={{ display: "flex", flexDirection: "column", gap: 18, height: "100%" }} className="animate-fade-in">
            {/* Status badges */}
            <div style={{ display: "flex", gap: 8 }}>
              <span className={`badge ${inspectLog.status === "success" ? "badge-success" : "badge-error"}`}>
                {inspectLog.status}
              </span>
              {inspectLog.pii_redacted && (
                <span className="badge badge-warning">
                  <ShieldCheck size={9} /> PII Redacted
                </span>
              )}
            </div>

            {/* Metadata grid */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
              {[
                { label: "Log UUID",      value: inspectLog.id },
                { label: "Timestamp",     value: new Date(inspectLog.timestamp).toISOString() },
                { label: "Latency",       value: `${inspectLog.latency_ms}ms` },
                { label: "Tokens (P/C/T)",value: `${inspectLog.tokens_prompt} / ${inspectLog.tokens_completion} / ${inspectLog.tokens_total}` },
                { label: "Provider",      value: inspectLog.provider },
                { label: "Model",         value: inspectLog.model },
              ].map((field) => (
                <div key={field.label} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-subtle)" }}>
                    {field.label}
                  </span>
                  <span style={{ fontSize: 12.5, fontFamily: "JetBrains Mono", color: "var(--text-muted)", wordBreak: "break-all" }}>
                    {field.value}
                  </span>
                </div>
              ))}
            </div>

            {/* Raw JSON */}
            <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
              <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-subtle)", marginBottom: 8 }}>
                Raw JSON Payload
              </span>
              <pre style={{
                flex: 1, background: "var(--bg-panel)", border: "1px solid var(--border)",
                borderRadius: 10, padding: "14px 16px",
                fontFamily: "JetBrains Mono", fontSize: 11.5, lineHeight: 1.65,
                color: "var(--text-muted)", overflowY: "auto", margin: 0,
              }}>
                {JSON.stringify(inspectLog, null, 2)}
              </pre>
            </div>

            <button className="btn" style={{ alignSelf: "flex-end" }} onClick={() => setInspectLog(null)}>
              Close
            </button>
          </div>
        )}
      </Drawer>
    </div>
  );
}
