import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
} from "react-native";
import * as SecureStore from "expo-secure-store";
import * as WebBrowser from "expo-web-browser";
import { splitwiseApi, gmailApi, telegramApi, authApi } from "../services/api";

interface Props {
  onLogout: () => void;
}

export default function SettingsScreen({ onLogout }: Props) {
  const [splitwiseConnected, setSplitwise] = useState<boolean | null>(null);
  const [gmailConnected, setGmail] = useState<boolean | null>(null);
  const [telegramLinked, setTelegram] = useState<boolean | null>(null);

  useEffect(() => {
    fetchStatuses();
  }, []);

  const fetchStatuses = async () => {
    try {
      const [sw, gm, tg] = await Promise.all([
        splitwiseApi.getStatus(),
        gmailApi.getStatus(),
        telegramApi.getStatus(),
      ]);
      setSplitwise(sw.data.connected);
      setGmail(gm.data.connected);
      setTelegram(tg.data.linked);
    } catch {
      // Silent
    }
  };

  const reconnect = async (service: "splitwise" | "gmail") => {
    try {
      const { data } =
        service === "splitwise"
          ? await splitwiseApi.getConnectUrl()
          : await gmailApi.getConnectUrl();
      await WebBrowser.openBrowserAsync(data.oauth_url);
      await fetchStatuses();
    } catch {
      Alert.alert("Error", `Could not reconnect ${service}`);
    }
  };

  const logout = async () => {
    const refresh = await SecureStore.getItemAsync("refresh_token");
    if (refresh) {
      try {
        await authApi.logout(refresh);
      } catch {
        // best effort
      }
    }
    await SecureStore.deleteItemAsync("access_token");
    await SecureStore.deleteItemAsync("refresh_token");
    onLogout();
  };

  const StatusIcon = ({ value }: { value: boolean | null }) =>
    value === null ? (
      <ActivityIndicator size="small" color="#6C63FF" />
    ) : (
      <Text>{value ? "✅" : "❌"}</Text>
    );

  return (
    <View style={styles.container}>
      <Text style={styles.heading}>Settings</Text>

      <View style={styles.card}>
        <Text style={styles.sectionTitle}>Connections</Text>

        <View style={styles.row}>
          <Text style={styles.rowLabel}>Splitwise</Text>
          <View style={styles.rowRight}>
            <StatusIcon value={splitwiseConnected} />
            <TouchableOpacity
              style={styles.reconnectBtn}
              onPress={() => reconnect("splitwise")}
            >
              <Text style={styles.reconnectText}>Reconnect</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={styles.divider} />

        <View style={styles.row}>
          <Text style={styles.rowLabel}>Gmail</Text>
          <View style={styles.rowRight}>
            <StatusIcon value={gmailConnected} />
            <TouchableOpacity
              style={styles.reconnectBtn}
              onPress={() => reconnect("gmail")}
            >
              <Text style={styles.reconnectText}>Reconnect</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={styles.divider} />

        <View style={styles.row}>
          <Text style={styles.rowLabel}>Telegram</Text>
          <StatusIcon value={telegramLinked} />
        </View>
      </View>

      <TouchableOpacity style={styles.logoutBtn} onPress={logout}>
        <Text style={styles.logoutText}>🚪 Logout</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5", padding: 20 },
  heading: { fontSize: 24, fontWeight: "bold", marginBottom: 24, paddingTop: 20 },
  card: {
    backgroundColor: "#fff",
    borderRadius: 16,
    padding: 20,
    shadowColor: "#000",
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 2,
    marginBottom: 24,
  },
  sectionTitle: { fontSize: 16, fontWeight: "700", color: "#888", marginBottom: 16 },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 4 },
  rowLabel: { fontSize: 16, fontWeight: "500" },
  rowRight: { flexDirection: "row", alignItems: "center", gap: 12 },
  reconnectBtn: {
    backgroundColor: "#EEF2FF",
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
  },
  reconnectText: { color: "#6C63FF", fontWeight: "600", fontSize: 13 },
  divider: { height: 1, backgroundColor: "#f0f0f0", marginVertical: 12 },
  logoutBtn: {
    backgroundColor: "#FEE2E2",
    borderRadius: 12,
    padding: 16,
    alignItems: "center",
  },
  logoutText: { color: "#EF4444", fontWeight: "600", fontSize: 16 },
});
