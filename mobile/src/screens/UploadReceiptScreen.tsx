import React, { useState } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  Image,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Alert,
} from "react-native";
import * as ImagePicker from "expo-image-picker";
import { receiptApi } from "../services/api";

interface ParsedReceipt {
  transaction_id: string;
  amount: number;
  merchant: string;
  date: string;
  currency: string;
  line_items: { name: string; price: number }[];
}

export default function UploadReceiptScreen() {
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [imageMime, setImageMime] = useState<string>("image/jpeg");
  const [parsed, setParsed] = useState<ParsedReceipt | null>(null);
  const [loading, setLoading] = useState(false);

  const pickImage = async (fromCamera: boolean) => {
    const perm = fromCamera
      ? await ImagePicker.requestCameraPermissionsAsync()
      : await ImagePicker.requestMediaLibraryPermissionsAsync();

    if (!perm.granted) {
      Alert.alert("Permission required", "Please grant permission to continue.");
      return;
    }

    const result = fromCamera
      ? await ImagePicker.launchCameraAsync({ quality: 0.8 })
      : await ImagePicker.launchImageLibraryAsync({ quality: 0.8 });

    if (!result.canceled && result.assets?.[0]) {
      setImageUri(result.assets[0].uri);
      setImageMime(result.assets[0].mimeType ?? "image/jpeg");
      setParsed(null);
    }
  };

  const parseReceipt = async () => {
    if (!imageUri) return;
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", {
        uri: imageUri,
        type: imageMime,
        name: "receipt.jpg",
      } as any);

      const { data } = await receiptApi.upload(formData);
      setParsed(data);
    } catch (err: any) {
      Alert.alert("Error", err.response?.data?.detail ?? "Could not parse receipt.");
    } finally {
      setLoading(false);
    }
  };

  const confirm = () => {
    Alert.alert(
      "✅ Submitted",
      "Check Telegram for next steps to add this to Splitwise."
    );
    setImageUri(null);
    setParsed(null);
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.heading}>Upload Receipt</Text>

      <View style={styles.pickerRow}>
        <TouchableOpacity style={styles.pickBtn} onPress={() => pickImage(true)}>
          <Text style={styles.pickBtnText}>📷 Camera</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.pickBtn} onPress={() => pickImage(false)}>
          <Text style={styles.pickBtnText}>🖼 Gallery</Text>
        </TouchableOpacity>
      </View>

      {imageUri && (
        <Image source={{ uri: imageUri }} style={styles.preview} resizeMode="contain" />
      )}

      {imageUri && !parsed && (
        <TouchableOpacity style={styles.parseBtn} onPress={parseReceipt} disabled={loading}>
          {loading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.parseBtnText}>🔍 Parse Receipt</Text>
          )}
        </TouchableOpacity>
      )}

      {parsed && (
        <View style={styles.parsedCard}>
          <Text style={styles.parsedTitle}>Extracted Details</Text>
          <Text style={styles.parsedRow}>
            <Text style={styles.label}>Merchant: </Text>{parsed.merchant}
          </Text>
          <Text style={styles.parsedRow}>
            <Text style={styles.label}>Amount: </Text>₹{parsed.amount}
          </Text>
          <Text style={styles.parsedRow}>
            <Text style={styles.label}>Date: </Text>{parsed.date ?? "N/A"}
          </Text>
          {parsed.line_items?.length > 0 && (
            <>
              <Text style={[styles.label, { marginTop: 12 }]}>Line Items:</Text>
              {parsed.line_items.map((item, i) => (
                <Text key={i} style={styles.parsedRow}>
                  • {item.name} — ₹{item.price}
                </Text>
              ))}
            </>
          )}

          <TouchableOpacity style={[styles.parseBtn, { marginTop: 20 }]} onPress={confirm}>
            <Text style={styles.parseBtnText}>✅ Confirm & Submit</Text>
          </TouchableOpacity>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5" },
  content: { padding: 20 },
  heading: { fontSize: 24, fontWeight: "bold", marginBottom: 20 },
  pickerRow: { flexDirection: "row", gap: 12, marginBottom: 20 },
  pickBtn: {
    flex: 1,
    backgroundColor: "#6C63FF",
    borderRadius: 10,
    padding: 14,
    alignItems: "center",
  },
  pickBtnText: { color: "#fff", fontWeight: "600", fontSize: 15 },
  preview: { width: "100%", height: 300, borderRadius: 12, marginBottom: 20 },
  parseBtn: {
    backgroundColor: "#6C63FF",
    borderRadius: 10,
    padding: 16,
    alignItems: "center",
    marginBottom: 16,
  },
  parseBtnText: { color: "#fff", fontWeight: "600", fontSize: 16 },
  parsedCard: {
    backgroundColor: "#fff",
    borderRadius: 12,
    padding: 20,
    shadowColor: "#000",
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 2,
  },
  parsedTitle: { fontSize: 18, fontWeight: "700", marginBottom: 12 },
  parsedRow: { fontSize: 15, marginBottom: 6, color: "#333" },
  label: { fontWeight: "600" },
});
