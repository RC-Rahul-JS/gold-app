from flask import Blueprint, request, jsonify
from bson.objectid import ObjectId
from datetime import datetime

accounting_bp = Blueprint("accounting", __name__)

from pymongo import MongoClient

MONGO_URI = "mongodb+srv://igold:gold0011@igold.eazpfbp.mongodb.net/?retryWrites=true&w=majority&appName=igold"
client = MongoClient(MONGO_URI)
db = client.get_database("golddb")

groups_collection = db["groups"] 
ledgers_collection = db["ledgers"] 


# ------------------ GROUPS ------------------
@accounting_bp.route("/groups", methods=["POST"])
def create_or_edit_group():
    try:
        data = request.json

        if "_id" in data and data["_id"]:  # EDIT
            groups_collection.update_one(
                {"_id": ObjectId(data["_id"])},
                {"$set": {
                    "GroupName": data["groupname"],
                    "GroupType": data["grouptype"]
                }}
            )
            return jsonify({"message": "Group updated successfully"}), 200
        else:  # CREATE
            count = groups_collection.count_documents({})
            mcode = f"G{count + 1}"

            new_group = {
                "Code": mcode,
                "GroupName": data["groupname"],
                "GroupType": data["grouptype"]
            }
            inserted = groups_collection.insert_one(new_group)
            new_group["_id"] = str(inserted.inserted_id)

            return jsonify({"message": "Group created successfully", "group": new_group}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@accounting_bp.route("/groups", methods=["GET"])
def get_all_groups():
    try:
        groups = list(groups_collection.find())
        for g in groups:
            g["_id"] = str(g["_id"])
        return jsonify(groups), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@accounting_bp.route("/groups/<id>", methods=["GET"])
def get_group_by_id(id):
    try:
        group = groups_collection.find_one({"_id": ObjectId(id)})
        if not group:
            return jsonify({"error": "Group not found"}), 404
        group["_id"] = str(group["_id"])
        return jsonify(group), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ------------------ LEDGERS ------------------
@accounting_bp.route("/ledgers", methods=["POST"])
def create_or_edit_ledger():
    try:
        data = request.json
        if "_id" in data and data["_id"]:
                updated_data={
                    "GroupType": data["grouptype"],
                    "LedgerName": data["ledgername"]
                }
                if "groupname" in data:
                    updated_data["Group_id"] = ObjectId(data["groupname"])  # EDIT

                ledgers_collection.update_one(
                    {"_id": ObjectId(data["_id"])},
                    {"$set": updated_data }
                )
                return jsonify({"message": "Ledger updated successfully"}), 200
        else:  # CREATE
            count = ledgers_collection.count_documents({})
            mcode = f"A{count + 1}"
            new_ledger = {
                "Code": mcode,
                "GroupType": data["grouptype"],
                "LedgerName": data["ledgername"]
            }
            new_ledger["Group_id"] = ObjectId(data["groupname"])
            print(new_ledger)
            inserted = ledgers_collection.insert_one(new_ledger)
            new_ledger["_id"] = str(inserted.inserted_id)

            return jsonify({"message": "Ledger created successfully"}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@accounting_bp.route("/ledgers", methods=["GET"])
def get_all_ledgers():
    try:
        pipeline = [
            {
                "$lookup": {
                    "from": "groups",             # groups_collection
                    "localField": "Group_id",     # field in ledgers
                    "foreignField": "_id",        # field in groups
                    "as": "group_info"
                }
            },
            {"$unwind": {"path": "$group_info", "preserveNullAndEmptyArrays": True}},
            {
                "$project": {
                    "_id": {"$toString": "$_id"},
                    "Code": 1,
                    "Group_id": {"$toString": "$Group_id"},
                    "LedgerName": 1,
                    "GroupName": {"$ifNull": ["$group_info.GroupName", "-"]},
                    "GroupType": {"$ifNull": ["$group_info.GroupType", "-"]}
                }
            }
        ]

        ledgers = list(ledgers_collection.aggregate(pipeline))
        return jsonify(ledgers), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500



@accounting_bp.route("/ledgers/<id>", methods=["GET"])
def get_ledger_by_id(id):
    try:
        ledger = ledgers_collection.find_one({"_id": ObjectId(id)})
        if not ledger:
            return jsonify({"error": "Ledger not found"}), 404
        ledger["_id"] = str(ledger["_id"])
        return jsonify(ledger), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
