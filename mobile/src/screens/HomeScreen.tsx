import React, { useCallback, useState } from "react";
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
} from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import { transactionsApi } from "../services/api";

type Status = "pending" | "added" | "skipped";

interface Transaction {
  id: string;
  amount: number;
  merchant: string;
  date: string;
  currency: string;
  source: string;
  status: Status;
}

const STATUS_COLORS: Record<Status, string> = {
  pending: "#F59E0B",
  added: "#10B981",
  skipped: "#9CA3AF",
};

interface Props {
  onUploadReceipt: () => void;
}

export default function HomeScreen({ onUploadReceipt }: Props) {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchTransactions = async () => {
    try {
      const { data } = await transactionsApi.list(20);
      setTransactions(data);
    } catch {
      // handled silently; user sees empty state
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useFocusEffect(
    useCallback(() => {
      setLoading(true);
      fetchTransactions();
    }, [])
  );

  const renderItem = ({ item }: { item: Transaction }) => (
    <View style={styles.card}>
      <View style={styles.cardLeft}>
        <Text style={styles.merchant} numberOfLines={1}>
          {item.merchant}
        </Text>
        <Text style={styles.date}>
          {new Date(item.date).toLocaleDateString("en-IN", {
            day: "numeric",
            month: "short",
            year: "numeric",
          })}
        </Text>
      </View>
      <View style={styles.cardRight}>
        <Text style={styles.amount}>
          ₹{item.amount.toLocaleString("en-IN")}
        </Text>
        <View
          style={[
            styles.badge,
            { backgroundColor: STATUS_COLORS[item.status] + "22" },
          ]}
        >
          <Text
            style={[styles.badgeText, { color: STATUS_COLORS[item.status] }]}
          >
            {item.status}
          </Text>
        </View>
      </View>
    </View>
  );

  return (
    <View style={styles.container}>
      <Text style={styles.heading}>Recent Transactions</Text>

      {loading ? (
        <ActivityIndicator size="large" color="#6C63FF" style={{ marginTop: 40 }} />
      ) : (
        <FlatList
          data={transactions}
          keyExtractor={(t) => t.id}
          renderItem={renderItem}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => {
                setRefreshing(true);
                fetchTransactions();
              }}
            />
          }
          ListEmptyComponent={
            <Text style={styles.empty}>No transactions yet. Bank emails will appear here.</Text>
          }
          contentContainerStyle={transactions.length === 0 && styles.emptyContainer}
        />
      )}

      <TouchableOpacity style={styles.fab} onPress={onUploadReceipt}>
        <Text style={styles.fabText}>📷</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5" },
  heading: { fontSize: 24, fontWeight: "bold", padding: 20, paddingBottom: 12 },
  card: {
    flexDirection: "row",
    backgroundColor: "#fff",
    marginHorizontal: 16,
    marginVertical: 6,
    borderRadius: 12,
    padding: 16,
    shadowColor: "#000",
    shadowOpacity: 0.05,
    shadowRadius: 6,
    elevation: 2,
    justifyContent: "space-between",
  },
  cardLeft: { flex: 1, marginRight: 12 },
  cardRight: { alignItems: "flex-end" },
  merchant: { fontSize: 16, fontWeight: "500", marginBottom: 4 },
  date: { color: "#888", fontSize: 13 },
  amount: { fontSize: 18, fontWeight: "700", color: "#1a1a1a", marginBottom: 6 },
  badge: { paddingHorizontal: 10, paddingVertical: 3, borderRadius: 12 },
  badgeText: { fontSize: 12, fontWeight: "600", textTransform: "capitalize" },
  emptyContainer: { flex: 1, justifyContent: "center", alignItems: "center" },
  empty: { color: "#999", textAlign: "center", paddingHorizontal: 32, lineHeight: 22 },
  fab: {
    position: "absolute",
    bottom: 28,
    right: 24,
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: "#6C63FF",
    justifyContent: "center",
    alignItems: "center",
    shadowColor: "#6C63FF",
    shadowOpacity: 0.4,
    shadowRadius: 8,
    elevation: 6,
  },
  fabText: { fontSize: 26 },
});
