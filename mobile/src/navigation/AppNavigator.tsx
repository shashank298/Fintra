import React, { useState, useEffect } from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import * as SecureStore from "expo-secure-store";
import { View, ActivityIndicator } from "react-native";

import AuthScreen from "../screens/AuthScreen";
import OnboardingScreen from "../screens/OnboardingScreen";
import HomeScreen from "../screens/HomeScreen";
import UploadReceiptScreen from "../screens/UploadReceiptScreen";
import SettingsScreen from "../screens/SettingsScreen";

const Stack = createNativeStackNavigator();
const Tab = createBottomTabNavigator();

function MainTabs({ onLogout }: { onLogout: () => void }) {
  const [showUpload, setShowUpload] = useState(false);

  if (showUpload) {
    return (
      <UploadReceiptScreen />
    );
  }

  return (
    <Tab.Navigator
      screenOptions={{
        tabBarActiveTintColor: "#6C63FF",
        tabBarInactiveTintColor: "#aaa",
        headerShown: false,
      }}
    >
      <Tab.Screen
        name="Home"
        options={{ tabBarLabel: "Home", tabBarIcon: () => null }}
      >
        {() => <HomeScreen onUploadReceipt={() => setShowUpload(true)} />}
      </Tab.Screen>
      <Tab.Screen
        name="Settings"
        options={{ tabBarLabel: "Settings", tabBarIcon: () => null }}
      >
        {() => <SettingsScreen onLogout={onLogout} />}
      </Tab.Screen>
    </Tab.Navigator>
  );
}

export default function AppNavigator() {
  const [state, setState] = useState<"loading" | "auth" | "onboarding" | "main">("loading");

  useEffect(() => {
    SecureStore.getItemAsync("access_token").then((token) => {
      setState(token ? "main" : "auth");
    });
  }, []);

  if (state === "loading") {
    return (
      <View style={{ flex: 1, justifyContent: "center", alignItems: "center" }}>
        <ActivityIndicator size="large" color="#6C63FF" />
      </View>
    );
  }

  return (
    <NavigationContainer>
      {state === "auth" && (
        <AuthScreen
          onAuthenticated={(isNew) => setState(isNew ? "onboarding" : "main")}
        />
      )}
      {state === "onboarding" && (
        <OnboardingScreen onComplete={() => setState("main")} />
      )}
      {state === "main" && (
        <MainTabs onLogout={() => setState("auth")} />
      )}
    </NavigationContainer>
  );
}
