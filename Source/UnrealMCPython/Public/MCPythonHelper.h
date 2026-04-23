// Copyright (c) 2025 GenOrca (by zenoengine). All Rights Reserved.

#pragma once

#include "Kismet/BlueprintFunctionLibrary.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraph/EdGraphPin.h"
#include "BehaviorTree/BehaviorTree.h"
#include "BehaviorTree/BlackboardData.h"
#include "Components/Widget.h"
#include "MCPythonHelper.generated.h"


USTRUCT(BlueprintType)
struct FMCPythonPinLinkInfo
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString NodeName;
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString NodeTitle;
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString PinName;
};

USTRUCT(BlueprintType)
struct FMCPythonBlueprintPinInfo
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString PinName;
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString FriendlyName;
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString Direction;
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString PinType;
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString PinSubType;
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString DefaultValue;
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    TArray<FMCPythonPinLinkInfo> LinkedTo;
};

USTRUCT(BlueprintType)
struct FMCPythonBlueprintNodeInfo
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString NodeName;
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString NodeTitle;
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString NodeComment;
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    TArray<FMCPythonBlueprintPinInfo> Pins;
};

USTRUCT(BlueprintType)
struct FMCPythonBTNodeInfo
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString NodeName;

    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString NodeClass;

    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    TArray<FString> DecoratorClasses;

    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    TArray<FString> DecoratorNames;

    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    TArray<FString> ServiceClasses;

    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    TArray<FString> ServiceNames;

    TArray<FMCPythonBTNodeInfo> Children;
};

UCLASS()
class UNREALMCPYTHON_API UMCPythonHelper : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    // 모든 에디터에서 열려있는 에셋 반환
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython", CallInEditor)
    static TArray<UObject*> GetAllEditedAssets();

    // (예시) 선택된 블루프린트 노드 반환
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython", CallInEditor)
    static TArray<UObject*> GetSelectedBlueprintNodes();

    // 선택된 블루프린트 노드의 연결 정보 반환
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython", CallInEditor)
    static TArray<FMCPythonBlueprintNodeInfo> GetSelectedBlueprintNodeInfos();

    // ─── Behavior Tree Helpers ──────────────────────────────────────────

    /** Get the full tree structure of a Behavior Tree as JSON string (accesses RootNode via C++) */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString GetBehaviorTreeStructure(UBehaviorTree* BehaviorTree);

    /** Set the Blackboard asset on a Behavior Tree (setter not exposed to Python) */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static bool SetBehaviorTreeBlackboard(UBehaviorTree* BehaviorTree, UBlackboardData* BlackboardData);

    /** Get detailed properties of a specific node by name, returned as JSON string */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString GetBehaviorTreeNodeDetails(UBehaviorTree* BehaviorTree, const FString& NodeName);

    /** Get details of selected nodes in the BT editor as JSON */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString GetSelectedBTNodes();

    /** Build a complete Behavior Tree from a JSON structure */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString BuildBehaviorTree(UBehaviorTree* BehaviorTree, const FString& TreeStructureJson);

    /** List all available BT node classes (composites, tasks, decorators, services) */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString ListBTNodeClasses();

    // ─── Blueprint Graph Helpers ──────────────────────────────────────────

    /** Get the full graph info (all nodes, pins, connections) for a Blueprint graph */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString GetBlueprintGraphInfo(UBlueprint* Blueprint, const FString& GraphName);

    /** List callable functions available in a Blueprint context */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString ListCallableFunctions(UBlueprint* Blueprint, const FString& Filter);

    /** List all variables defined in a Blueprint */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString ListBlueprintVariables(UBlueprint* Blueprint);

    /** Add a single node to a Blueprint graph from JSON description */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString AddBlueprintNode(UBlueprint* Blueprint, const FString& GraphName, const FString& NodeJson);

    /** Connect two pins in a Blueprint graph */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString ConnectBlueprintPins(UBlueprint* Blueprint, const FString& GraphName,
        const FString& SourceNodeName, const FString& SourcePinName,
        const FString& TargetNodeName, const FString& TargetPinName);

    /** Remove a node from a Blueprint graph */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString RemoveBlueprintNode(UBlueprint* Blueprint, const FString& GraphName,
        const FString& NodeName);

    /** Build a Blueprint graph from JSON adjacency list (nodes + connections) */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString BuildBlueprintGraph(UBlueprint* Blueprint, const FString& GraphName,
        const FString& GraphJson);

    /** Compile a Blueprint and return the result */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString CompileBlueprint(UBlueprint* Blueprint);

    // ─── UMG Widget Blueprint Helpers ─────────────────────────────────────────

    /** Get widget tree info (root widget, all widgets) as JSON */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString UmgGetWidgetInfo(UBlueprint* WidgetBP);

    /** Add a widget to the widget tree. ParentName="" means auto-root or root panel. Returns JSON. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString UmgAddWidget(UBlueprint* WidgetBP, const FString& WidgetType, const FString& WidgetName, const FString& ParentName);

    /** Find a widget by name in the widget tree. Returns nullptr if not found. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static UWidget* UmgFindWidget(UBlueprint* WidgetBP, const FString& WidgetName);

    /** Remove a widget from the widget tree. Returns JSON. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString UmgRemoveWidget(UBlueprint* WidgetBP, const FString& WidgetName);
};
