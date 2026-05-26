import axios from "axios";
import type { components } from "./schema";

// Types extracted directly from openapi-typescript generated schema
export type ConversationResponse = components["schemas"]["ConversationResponse"];
export type ConversationCreate = components["schemas"]["ConversationCreate"];
export type MessageResponse = components["schemas"]["MessageResponse"];
export type ConversationDeleteResponse = components["schemas"]["ConversationDeleteResponse"];
export type ChatRequest = components["schemas"]["ChatRequest"];
export type MetricsResponse = components["schemas"]["MetricsResponse"];
export type TimeseriesPointResponse = components["schemas"]["TimeseriesPointResponse"];
export type TelemetryLogResponse = components["schemas"]["TelemetryLogResponse"];

// Axios instance with base URL configuration
export const api = axios.create({
  baseURL: "http://localhost:8005",
  headers: {
    "Content-Type": "application/json",
  },
});

export const apiService = {
  /**
   * Retrieves the lists of active conversations
   */
  async getConversations(): Promise<ConversationResponse[]> {
    const res = await api.get<ConversationResponse[]>("/api/conversations");
    return res.data;
  },

  /**
   * Creates a new conversation session
   */
  async createConversation(title?: string): Promise<ConversationResponse> {
    const payload: ConversationCreate = { title: title || null };
    const res = await api.post<ConversationResponse>("/api/conversations", payload);
    return res.data;
  },

  /**
   * Deletes and cancels a conversation session
   */
  async deleteConversation(convId: string): Promise<ConversationDeleteResponse> {
    const res = await api.delete<ConversationDeleteResponse>(`/api/conversations/${convId}`);
    return res.data;
  },

  /**
   * Resumes and retrieves messages of an active conversation session
   */
  async getMessages(convId: string): Promise<MessageResponse[]> {
    const res = await api.get<MessageResponse[]>(`/api/conversations/${convId}/messages`);
    return res.data;
  },

  /**
   * Fetches key operational metrics averages
   */
  async getMetrics(): Promise<MetricsResponse> {
    const res = await api.get<MetricsResponse>("/api/analytics/metrics");
    return res.data;
  },

  /**
   * Fetches chronological telemetry datastructure
   */
  async getTimeseries(): Promise<TimeseriesPointResponse[]> {
    const res = await api.get<TimeseriesPointResponse[]>("/api/analytics/timeseries");
    return res.data;
  },

  /**
   * Fetches recent inference logs
   */
  async getRecentLogs(): Promise<TelemetryLogResponse[]> {
    const res = await api.get<TelemetryLogResponse[]>("/api/analytics/logs");
    return res.data;
  },
};
