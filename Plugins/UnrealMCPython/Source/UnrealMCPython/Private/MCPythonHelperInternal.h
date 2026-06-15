// Copyright (c) 2025 GenOrca (by zenoengine). All Rights Reserved.
// Shared internal helpers for the split MCPythonHelper_*.cpp translation units.
#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonWriter.h"
#include "Serialization/JsonSerializer.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraph/EdGraphPin.h"
#include "Engine/Blueprint.h"

inline FString MakeJsonError(const FString& Message)
{
    TSharedPtr<FJsonObject> Obj = MakeShareable(new FJsonObject());
    Obj->SetBoolField(TEXT("success"), false);
    Obj->SetStringField(TEXT("message"), Message);
    FString Out;
    TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Out);
    FJsonSerializer::Serialize(Obj.ToSharedRef(), W);
    return Out;
}

inline FString MakeJsonSuccess(const FString& Message)
{
    TSharedPtr<FJsonObject> Obj = MakeShareable(new FJsonObject());
    Obj->SetBoolField(TEXT("success"), true);
    Obj->SetStringField(TEXT("message"), Message);
    FString Out;
    TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Out);
    FJsonSerializer::Serialize(Obj.ToSharedRef(), W);
    return Out;
}

inline FString SerializeJsonObj(TSharedPtr<FJsonObject> Obj)
{
    FString Out;
    TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Out);
    FJsonSerializer::Serialize(Obj.ToSharedRef(), W);
    return Out;
}

inline UEdGraph* FindGraphByName(UBlueprint* Blueprint, const FString& GraphName)
{
    for (UEdGraph* Graph : Blueprint->UbergraphPages)
    {
        if (Graph && Graph->GetName() == GraphName)
            return Graph;
    }
    for (UEdGraph* Graph : Blueprint->FunctionGraphs)
    {
        if (Graph && Graph->GetName() == GraphName)
            return Graph;
    }
    return nullptr;
}

inline UEdGraphNode* FindBPNodeByName(UEdGraph* Graph, const FString& NodeName)
{
    for (UEdGraphNode* Node : Graph->Nodes)
    {
        if (Node && Node->GetName() == NodeName)
            return Node;
    }
    return nullptr;
}

inline UEdGraphPin* FindPinByName(UEdGraphNode* Node, const FString& PinName, EEdGraphPinDirection Direction = EGPD_MAX)
{
    for (UEdGraphPin* Pin : Node->Pins)
    {
        if (!Pin || Pin->bHidden) continue;
        if (Direction != EGPD_MAX && Pin->Direction != Direction) continue;

        // Match by internal name
        if (Pin->GetName() == PinName)
            return Pin;
        // Match by friendly name
        FString Friendly = Pin->PinFriendlyName.ToString();
        if (!Friendly.IsEmpty() && Friendly == PinName)
            return Pin;
    }
    return nullptr;
}
